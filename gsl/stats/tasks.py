import csv
import io
import logging
from datetime import datetime, timezone

import requests
from celery import shared_task
from django.conf import settings

from gsl.celery import TASK_PRIORITY_LOW
from gsl.projet.constants import DS_STATE_VALUES

from .models import FondsVertImportState, Subvention

logger = logging.getLogger(__name__)

DGCL_DATASET_ID = "6176785207139a929a2776fe"
DGCL_API_URL = f"https://www.data.gouv.fr/api/1/datasets/{DGCL_DATASET_ID}/"

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


@shared_task(priority=TASK_PRIORITY_LOW)
def fetch_subventions_dgcl():
    response = requests.get(DGCL_API_URL, timeout=30)
    response.raise_for_status()
    dataset = response.json()

    resources = [
        r for r in dataset.get("resources", []) if r.get("format", "").lower() == "csv"
    ]
    logger.info(f"Trouvé {len(resources)} ressources CSV dans le jeu de données DGCL")

    # La DGCL republie l'intégralité du jeu de données à chaque mise à jour,
    # sans identifiant stable par ligne : pas de déduplication ni d'upsert
    # possible, on vide et on reconstruit entièrement ces lignes à chaque
    # import (cf. Subvention.__doc__).
    nb_deleted, _ = Subvention.objects.filter(source=Subvention.SOURCE_DGCL).delete()
    logger.info(f"{nb_deleted} lignes DGCL existantes supprimées avant réimport")

    bilan = {}
    for resource in resources:
        url = resource.get("url")
        if not url:
            continue
        nb_imported, errors = _import_csv_resource(url)
        title = resource.get("title", url)
        bilan[title] = {"imported": nb_imported, "errors": len(errors)}
        logger.info(f"{title}: {nb_imported} lignes importées, {len(errors)} erreurs")
        for err in errors:
            logger.error(
                f"  Erreur import ligne {err['line']}: {err['error']} — {err['row']}"
            )

    return bilan


def _import_csv_resource(url):
    """Importe une ressource CSV DGCL : chaque ligne valide devient une
    `Subvention`, insérées en une fois par `bulk_create` (pas d'upsert, cf.
    `fetch_subventions_dgcl`)."""
    response = requests.get(url, timeout=120, stream=True)
    response.raise_for_status()

    content = b"".join(response.iter_content(chunk_size=65536))
    # utf-8-sig strips the BOM (﻿) that DGCL CSVs include, which would otherwise
    # corrupt the first column header key.
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    subventions = []
    errors = []

    for line_num, row in enumerate(reader, start=2):
        try:
            subvention = _build_dgcl_subvention(row)
        except Exception as e:
            errors.append(
                {
                    "line": line_num,
                    "error": str(e),
                    "row": {
                        k: v
                        for k, v in row.items()
                        if k
                        in ("exercice", "dispositif", "beneficiaire_siren", "intitule")
                    },
                }
            )
            continue
        if subvention is not None:
            subventions.append(subvention)

    Subvention.objects.bulk_create(subventions)
    return len(subventions), errors


def _build_dgcl_subvention(row) -> Subvention | None:
    exercice = _parse_int(
        row.get("exercice") or row.get("annee") or row.get("Exercice")
    )
    dispositif = (row.get("dispositif") or row.get("Dispositif") or "").strip().upper()
    programme = _parse_int(row.get("programme") or row.get("Programme") or "0") or 0
    beneficiaire_siren = (
        row.get("beneficiaire_siren")
        or row.get("Bénéficiaire - SIREN")
        or row.get("siret_beneficiaire")
        or ""
    ).strip()[:9]
    intitule = (
        row.get("intitule") or row.get("Intitulé du projet") or row.get("objet") or ""
    ).strip()
    cout_total_raw = (
        row.get("cout_ht")
        or row.get("Coût total HT du projet")
        or row.get("montant_total_ht")
        or "0"
    )
    montant_attribue_raw = (
        row.get("subvention")
        or row.get("Montant de la subvention accordée")
        or row.get("montant_subvention")
        or "0"
    )
    dep_code = (
        row.get("beneficiaire_dep")
        or row.get("Bénéficiaire - Département")
        or row.get("departement")
        or ""
    ).strip()
    insee_code = (
        row.get("beneficiaire_code_insee")
        or row.get("Bénéficiaire - Code INSEE")
        or row.get("code_insee")
        or ""
    ).strip()

    if not exercice or not dispositif or not beneficiaire_siren or not intitule:
        return None

    # La DSID (Dotation de soutien à l'investissement des départements) ne
    # concerne pas les communes/EPCI suivis par Turgot : on l'ignore.
    if dispositif == "DSID":
        return None

    departement = _resolve_departement(dep_code)
    commune = _resolve_commune(insee_code)

    # bulk_create (cf. _import_csv_resource) contourne Subvention.save(), donc
    # on renseigne unique_key ici.
    unique_key = Subvention.compute_unique_key(
        Subvention.SOURCE_DGCL,
        exercice=exercice,
        dispositif=dispositif,
        siren=beneficiaire_siren,
        intitule=intitule,
    )
    return Subvention(
        unique_key=unique_key,
        source=Subvention.SOURCE_DGCL,
        exercice=exercice,
        dispositif=dispositif,
        siren=beneficiaire_siren,
        intitule=intitule,
        programme=programme,
        departement=departement,
        commune=commune,
        cout_total=_parse_decimal(cout_total_raw),
        montant_attribue=_parse_decimal(montant_attribue_raw),
    )


@shared_task(priority=TASK_PRIORITY_LOW)
def fetch_subventions_fonds_vert():
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

    departement = _resolve_departement(sc.get("code_departement", ""))
    commune = _resolve_commune(sc.get("code_commune", ""))

    unique_key = Subvention.compute_unique_key(
        Subvention.SOURCE_FONDS_VERT, dossier_number=dossier_number
    )
    _, created = Subvention.objects.update_or_create(
        unique_key=unique_key,
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


def _resolve_departement(code):
    from gsl_core.models import Departement

    if not code:
        return None
    # DGCL CSVs zero-pad to 3 chars (e.g. "001") but Departement.insee_code uses
    # 2 chars for mainland ("01") and 3 for overseas ("971"-"976") or Corsica ("2A").
    stripped = code.lstrip("0") or "0"
    candidates = dict.fromkeys([code, stripped.zfill(2), stripped.zfill(3)])
    for candidate in candidates:
        try:
            return Departement.objects.get(insee_code=candidate)
        except Departement.DoesNotExist:
            pass
    return None


def _resolve_commune(code_insee):
    from gsl_core.models import Commune

    if not code_insee:
        return None
    try:
        return Commune.objects.get(insee_code=code_insee)
    except Commune.DoesNotExist:
        return None


def _parse_int(value):
    if not value:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _parse_decimal(value):
    if not value:
        return 0
    cleaned = str(value).strip().replace(",", ".").replace(" ", "").replace("\xa0", "")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0
