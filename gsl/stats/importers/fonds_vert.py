import logging
from datetime import timezone

from django.utils.dateparse import parse_datetime

from gsl.projet.constants import DS_STATE_VALUES
from gsl_core.api.fonds_vert import FondsVertClient, FondsVertCredentialsMissing

from ..models import FondsVertImportState, Subvention
from .utils import resolve_commune, resolve_departement

logger = logging.getLogger(__name__)

# Le Fonds Vert n'a pas de "dispositif"/"programme" propre côté DS : on retient
# la nomenclature budgétaire de l'État (programme 380 - Fonds d'accélération de
# la transition écologique dans les territoires) pour rester homogène avec les
# lignes DGCL (DETR/DSIL/DPV, programme 119).
FONDS_VERT_DISPOSITIF = "FONDS VERT"
FONDS_VERT_PROGRAMME = 380

# L'API Fonds Vert renvoie le statut du dossier sous forme de libellé DS
# ("Accepté", "En instruction", ...) : on le fait correspondre au code
# Subvention.status (choices=DS_STATE_VALUES) attendu.
_FONDS_VERT_STATUS_LABEL_TO_CODE = {label: code for code, label in DS_STATE_VALUES}


def import_fonds_vert_subventions(restart=False):
    """`restart` : ignore le curseur de reprise et repart de la page 1
    (utilisé par la management command `import_subventions_fonds_vert
    --restart`)."""
    try:
        client = FondsVertClient()
    except FondsVertCredentialsMissing as e:
        logger.error(str(e))
        return {}
    state = FondsVertImportState.load()
    start_page = 1 if restart else state.data.get("last_page", 0) + 1
    if start_page > 1:
        logger.info("Fonds Vert: reprise à la page %d", start_page)

    nb_created = nb_updated = nb_errors = 0

    for page, items in client.iter_dossiers_pages(start_page=start_page):
        created, updated, errors = _import_fonds_vert_page(items)
        nb_created += created
        nb_updated += updated
        nb_errors += len(errors)
        for err in errors:
            logger.error(
                "Erreur import dossier Fonds Vert #%s: %s",
                err["dossier_number"],
                err["error"],
            )
        # Une page est entièrement traitée : on avance le curseur pour pouvoir
        # reprendre ici si la tâche est interrompue avant la fin.
        state.data["last_page"] = page
        state.save(update_fields=["data", "updated_at"])

    # Synchronisation complète : on repartira de la page 1 au prochain lancement.
    state.data["last_page"] = 0
    state.save(update_fields=["data", "updated_at"])

    logger.info(
        "Fonds Vert: %d créés, %d mis à jour, %d erreurs",
        nb_created,
        nb_updated,
        nb_errors,
    )
    return {"created": nb_created, "updated": nb_updated, "errors": nb_errors}


def _import_fonds_vert_page(items):
    """Importe chaque dossier Fonds Vert d'une page (cf.
    `gsl_core.api.fonds_vert.iter_dossiers_pages`). Retourne
    `(nb_created, nb_updated, errors)`."""
    nb_created = nb_updated = 0
    errors = []
    for item in items:
        try:
            created = _import_fonds_vert_dossier(item)
        except Exception as e:
            sc = item.get("socle_commun", {})
            errors.append({"dossier_number": sc.get("dossier_number"), "error": str(e)})
            continue
        if created:
            nb_created += 1
        else:
            nb_updated += 1
    return nb_created, nb_updated, errors


def _import_fonds_vert_dossier(item: dict) -> bool:
    sc = item.get("socle_commun", {})

    dossier_number = sc.get("dossier_number")
    siret = (sc.get("siret") or "").strip()

    if not dossier_number or not siret:
        return False

    departement = resolve_departement(sc.get("code_departement", ""))
    commune = resolve_commune(sc.get("code_commune", ""))

    _, created = Subvention.objects.update_or_create(
        importer_key=_compute_fonds_vert_importer_key(dossier_number),
        source=Subvention.SOURCE_FONDS_VERT,
        defaults={
            "dossier_number": dossier_number,
            "siren": siret[:9],
            "exercice": sc.get("annee_millesime") or 0,
            "dispositif": FONDS_VERT_DISPOSITIF,
            "programme": FONDS_VERT_PROGRAMME,
            "intitule": sc.get("nom_du_projet") or "",
            "status": _resolve_fonds_vert_status(sc.get("statut")),
            "departement": departement,
            "commune": commune,
            "montant_demande": sc.get("montant_aide_demandee_fond_vert") or 0,
            "montant_attribue": sc.get("montant_subvention_attribuee"),
            "cout_total": sc.get("total_des_depenses") or 0,
            "date_depot": _parse_datetime(sc.get("date_depot")),
        },
    )
    return created


def _compute_fonds_vert_importer_key(dossier_number):
    return f"{dossier_number}"


def _resolve_fonds_vert_status(raw_statut) -> str:
    return _FONDS_VERT_STATUS_LABEL_TO_CODE.get((raw_statut or "").strip(), "")


def _parse_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
