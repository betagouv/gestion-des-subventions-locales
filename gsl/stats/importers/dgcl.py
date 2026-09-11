import csv
import io
import logging

import requests

from ..models import Subvention
from .utils import resolve_commune, resolve_departement

logger = logging.getLogger(__name__)

DGCL_DATASET_ID = "6176785207139a929a2776fe"
DGCL_API_URL = f"https://www.data.gouv.fr/api/1/datasets/{DGCL_DATASET_ID}/"


def import_dgcl_subventions():
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
    `import_dgcl_subventions`)."""
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

    departement = resolve_departement(dep_code)
    commune = resolve_commune(insee_code)

    return Subvention(
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
