import csv
import io
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction

from gsl_core.api.data_gouv import get_dataset_resources

from ..models import Subvention
from .utils import resolve_commune, resolve_departement

logger = logging.getLogger(__name__)

DGCL_DATASET_ID = "6176785207139a929a2776fe"


@transaction.atomic
def import_dgcl_subventions(show_dsid=False):
    """`show_dsid` : affiche aussi, dans le bilan journalisé, les lignes
    ignorées car en dispositif DSID (masquées par défaut, cf.
    `_log_invalidated_lines`)."""
    resources = get_dataset_resources(DGCL_DATASET_ID, "csv")
    logger.info(f"Trouvé {len(resources)} ressources CSV dans le jeu de données DGCL")

    # La DGCL republie l'intégralité du jeu de données à chaque mise à jour,
    # sans identifiant stable par ligne : pas de déduplication ni d'upsert
    # possible, on vide et on reconstruit entièrement ces lignes à chaque
    # import (cf. Subvention.__doc__). La transaction évite de se retrouver
    # avec une table vidée si le réimport plante en cours de route.
    nb_deleted, _ = Subvention.objects.filter(source=Subvention.SOURCE_DGCL).delete()
    logger.info(f"{nb_deleted} lignes DGCL existantes supprimées avant réimport")

    for resource in resources:
        url = resource["url"]
        nb_validated, invalid_rows = _import_csv_resource(url)
        title = resource.get("title", url)
        logger.info(
            f"{title}: {nb_validated} lignes validées, {len(invalid_rows)} lignes invalidées"
        )
        _log_invalidated_lines(invalid_rows, show_dsid=show_dsid)


class DgclRowSkipped(Exception):
    """Levée par `_build_dgcl_subvention` pour signaler qu'une ligne doit
    être ignorée. `reason` est un libellé regroupable (sert de clé pour le
    bilan par type d'erreur) ; `field` n'est renseigné que pour un champ
    obligatoire manquant, pour permettre un sous-bilan par champ."""

    def __init__(self, reason, field_name=None):
        super().__init__(reason)
        self.reason = reason
        self.field = field_name


@dataclass
class InvalidRowsSummary:
    """Un bilan : nombre de lignes concernées + liste de ces lignes."""

    reason: str
    count: int = 0
    lines: list[int] = field(default_factory=list)


@dataclass
class InvalidRow:
    line: int
    reason: str
    field: str | None = None


# Motif de `DgclRowSkipped` pour un dispositif DSID : hors périmètre Turgot
# par construction (cf. `_build_dgcl_subvention`), pas un problème de
# données à corriger — masqué du bilan journalisé par défaut.
DSID_SKIPPED_REASON = "dispositif DSID (hors périmètre Turgot)"


def _import_csv_resource(url):
    """Importe une ressource CSV DGCL : chaque ligne valide devient une
    `Subvention`, insérées en une fois par `bulk_create` (pas d'upsert, cf.
    `import_dgcl_subventions`). Retourne `(nb_validated, invalid_rows)` —
    `invalid_rows` détaille chaque ligne pour laquelle `_build_dgcl_subvention`
    a levé une exception (`DgclRowSkipped` ou autre), avec son numéro de
    ligne et la raison."""
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    # utf-8-sig strips the BOM (﻿) that DGCL CSVs include, which would otherwise
    # corrupt the first column header key.
    text = response.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    subventions = []
    invalid_rows: list[InvalidRow] = []

    for line_num, row in enumerate(reader, start=2):
        try:
            subventions.append(_build_dgcl_subvention(row))
        except DgclRowSkipped as e:
            invalid_rows.append(InvalidRow(line_num, e.reason, e.field))
        except Exception as e:
            invalid_rows.append(InvalidRow(line_num, str(e), None))

    Subvention.objects.bulk_create(subventions)
    return len(subventions), invalid_rows


def _build_dgcl_subvention(row) -> Subvention:
    """Lève `DgclRowSkipped` si la ligne doit être ignorée (champ obligatoire
    manquant, ou dispositif DSID hors périmètre Turgot)."""
    exercice = _parse_int(
        row.get("exercice") or row.get("annee") or row.get("Exercice")
    )
    dispositif = (row.get("dispositif") or row.get("Dispositif") or "").strip().upper()

    # La DSID (Dotation de soutien à l'investissement des départements) ne
    # concerne pas les communes/EPCI suivis par Turgot : on l'ignore.
    if dispositif == "DSID":
        raise DgclRowSkipped(DSID_SKIPPED_REASON)

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

    for field_name, value in (
        ("exercice", exercice),
        ("dispositif", dispositif),
        ("beneficiaire_siren", beneficiaire_siren),
        ("intitule", intitule),
    ):
        if not value:
            raise DgclRowSkipped("champ obligatoire manquant", field_name=field_name)

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
        return Decimal(0)
    cleaned = str(value).strip().replace(",", ".").replace(" ", "").replace("\xa0", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal(0)


def _log_invalidated_lines(invalid_rows: list[InvalidRow], show_dsid=False) -> None:
    """Regroupe (cf. `_summarize_invalid_rows`) et journalise (info) le
    bilan des lignes invalides. Le motif DSID (`DSID_SKIPPED_REASON`) est
    masqué par défaut ; passer `show_dsid=True` pour l'afficher aussi."""
    invalid_rows_summaries = _summarize_invalid_rows(invalid_rows)
    for invalid_rows_summary in invalid_rows_summaries:
        if not show_dsid and invalid_rows_summary.reason == DSID_SKIPPED_REASON:
            continue
        logger.info(
            f"    {invalid_rows_summary.reason} : {invalid_rows_summary.count} ligne(s) — lignes {invalid_rows_summary.lines}"
        )


def _summarize_invalid_rows(
    invalid_rows: list[InvalidRow],
) -> list[InvalidRowsSummary]:
    bilans_by_reason: dict[str, InvalidRowsSummary] = {}
    for invalid_row in invalid_rows:
        reason = invalid_row.reason
        if invalid_row.field:
            reason += f" - {invalid_row.field}"

        bilan = bilans_by_reason.setdefault(reason, InvalidRowsSummary(reason=reason))
        bilan.count += 1
        bilan.lines.append(invalid_row.line)
    return list(bilans_by_reason.values())
