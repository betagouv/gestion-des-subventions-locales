import logging
from datetime import datetime, timezone

import requests
from django.conf import settings

from gsl.projet.constants import DS_STATE_VALUES

from ..models import FondsVertImportState, Subvention
from .utils import resolve_commune, resolve_departement

logger = logging.getLogger(__name__)

FONDS_VERT_BASE_URL = "https://api-fonds-vert.datahub.din.developpement-durable.gouv.fr"
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


def import_fonds_vert_subventions():
    username = settings.FONDS_VERT_USERNAME
    password = settings.FONDS_VERT_PASSWORD
    if not username or not password:
        logger.error(
            "FONDS_VERT_USERNAME / FONDS_VERT_PASSWORD non définis — import annulé"
        )
        return {}

    token = _fonds_vert_login(username, password)
    state = FondsVertImportState.load()
    last_page = state.data.get("last_page", 0)
    if last_page:
        logger.info("Fonds Vert: reprise à la page %d", last_page + 1)

    nb_created = nb_updated = nb_errors = 0

    for page, created, updated, errors in _iter_fonds_vert_pages(
        token, start_page=last_page + 1
    ):
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


def _iter_fonds_vert_pages(token: str, start_page: int = 1, per_page: int = 500):
    """Parcourt `/fonds_vert/v2/dossiers` à partir de `start_page` et importe chaque
    dossier. Cède `(page, nb_created, nb_updated, errors)` après chaque page complète,
    pour permettre aux appelants de persister un curseur de reprise et de reporter la
    progression au fil de l'eau plutôt qu'en fin d'import complet.
    """
    page = start_page
    while True:
        data = _fonds_vert_get(
            token, "/fonds_vert/v2/dossiers", page=page, per_page=per_page
        )
        items = data.get("data", [])
        if not items:
            return

        nb_created = nb_updated = 0
        errors = []
        for item in items:
            try:
                created = _import_fonds_vert_dossier(item)
            except Exception as e:
                sc = item.get("socle_commun", {})
                errors.append(
                    {"dossier_number": sc.get("dossier_number"), "error": str(e)}
                )
                continue
            if created:
                nb_created += 1
            else:
                nb_updated += 1

        yield page, nb_created, nb_updated, errors

        if data.get("next_page") is None:
            return
        page += 1


def _fonds_vert_login(username: str, password: str) -> str:
    resp = requests.post(
        f"{FONDS_VERT_BASE_URL}/fonds_vert/login",
        headers={"Accept": "application/json"},
        data={"username": username, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _fonds_vert_get(token: str, path: str, **params) -> dict:
    resp = requests.get(
        f"{FONDS_VERT_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


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
        defaults={
            "source": Subvention.SOURCE_FONDS_VERT,
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
    return f"{Subvention.SOURCE_FONDS_VERT}:{dossier_number}"


def _resolve_fonds_vert_status(raw_statut) -> str:
    return _FONDS_VERT_STATUS_LABEL_TO_CODE.get((raw_statut or "").strip(), "")


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None
