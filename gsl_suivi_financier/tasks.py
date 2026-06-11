import csv
import io
import logging

import requests
from celery import shared_task

from gsl.celery import TASK_PRIORITY_LOW

logger = logging.getLogger(__name__)

DGCL_DATASET_ID = "6176785207139a929a2776fe"
DGCL_API_URL = f"https://www.data.gouv.fr/api/1/datasets/{DGCL_DATASET_ID}/"


@shared_task(priority=TASK_PRIORITY_LOW)
def fetch_subventions_dgcl():
    response = requests.get(DGCL_API_URL, timeout=30)
    response.raise_for_status()
    dataset = response.json()

    resources = [
        r for r in dataset.get("resources", []) if r.get("format", "").lower() == "csv"
    ]
    logger.info(f"Trouvé {len(resources)} ressources CSV dans le jeu de données DGCL")

    bilan = {}
    for resource in resources:
        url = resource.get("url")
        if not url:
            continue
        nb_created, nb_updated, errors = _import_csv_resource(url)
        title = resource.get("title", url)
        bilan[title] = {
            "created": nb_created,
            "updated": nb_updated,
            "errors": len(errors),
        }
        logger.info(
            f"{title}: {nb_created} créés, {nb_updated} mis à jour, {len(errors)} erreurs"
        )
        for err in errors:
            logger.error(
                f"  Erreur import ligne {err['line']}: {err['error']} — {err['row']}"
            )

    return bilan


def _import_csv_resource(url):
    response = requests.get(url, timeout=120, stream=True)
    response.raise_for_status()

    content = b"".join(response.iter_content(chunk_size=65536))
    # utf-8-sig strips the BOM (﻿) that DGCL CSVs include, which would otherwise
    # corrupt the first column header key.
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    nb_created = 0
    nb_updated = 0
    errors = []

    for line_num, row in enumerate(reader, start=2):
        try:
            created = _import_row(row)
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
        if created:
            nb_created += 1
        else:
            nb_updated += 1

    return nb_created, nb_updated, errors


def _import_row(row):
    from .models import Beneficiaire, SubventionDgcl

    exercice = _parse_int(
        row.get("exercice") or row.get("annee") or row.get("Exercice")
    )
    dispositif = (row.get("dispositif") or row.get("Dispositif") or "").strip().upper()
    programme = _parse_int(row.get("programme") or row.get("Programme") or "0") or 0
    beneficiaire_type = (
        row.get("beneficiaire_type")
        or row.get("Bénéficiaire - Type")
        or row.get("type_beneficiaire")
        or ""
    ).strip()
    beneficiaire_siren = (
        row.get("beneficiaire_siren")
        or row.get("Bénéficiaire - SIREN")
        or row.get("siret_beneficiaire")
        or ""
    ).strip()[:9]
    beneficiaire_nom = (
        row.get("beneficiaire_nom")
        or row.get("Bénéficiaire - Nom")
        or row.get("nom_beneficiaire")
        or ""
    ).strip()[:200]
    intitule = (
        row.get("intitule") or row.get("Intitulé du projet") or row.get("objet") or ""
    ).strip()
    cout_ht_raw = (
        row.get("cout_ht")
        or row.get("Coût total HT du projet")
        or row.get("montant_total_ht")
        or "0"
    )
    subvention_raw = (
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
        return False

    departement = _resolve_departement(dep_code)
    commune = _resolve_commune(insee_code)

    # Upsert le bénéficiaire — le nom/type reflète toujours la dernière donnée importée.
    beneficiaire, _ = Beneficiaire.objects.update_or_create(
        siren=beneficiaire_siren,
        defaults={"nom": beneficiaire_nom, "type": beneficiaire_type},
    )

    _, created = SubventionDgcl.objects.update_or_create(
        exercice=exercice,
        dispositif=dispositif,
        beneficiaire=beneficiaire,
        intitule=intitule,
        defaults={
            "programme": programme,
            "departement": departement,
            "commune": commune,
            "cout_ht": _parse_decimal(cout_ht_raw),
            "subvention": _parse_decimal(subvention_raw),
        },
    )
    return created


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
