import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from gsl_core.models import Commune, Departement

DEPARTEMENTS: dict[str, Departement] = {}
COMMUNES: dict[str, Commune] = {}


def resolve_departement(code):
    """Résout un code INSEE département en `Departement`. Charge tous les
    départements en mémoire au premier appel plutôt que de faire une requête
    par ligne importée (une centaine de lignes, ça tient largement en RAM)."""
    if not code:
        return None

    if not DEPARTEMENTS:
        for d in Departement.objects.all():
            DEPARTEMENTS[d.insee_code] = d

    # DGCL CSVs zero-pad to 3 chars (e.g. "001") but Departement.insee_code uses
    # 2 chars for mainland ("01") and 3 for overseas ("971"-"976") or Corsica ("2A").
    stripped = code.lstrip("0") or "0"
    for candidate in dict.fromkeys([code, stripped.zfill(2), stripped.zfill(3)]):
        if candidate in DEPARTEMENTS:
            return DEPARTEMENTS[candidate]
    return None


def resolve_commune(code_insee):
    """Résout un code INSEE commune en `Commune`. Charge toutes les communes
    en mémoire au premier appel plutôt que de faire une requête par ligne
    importée. Recherche insensible à la casse : certains imports (ex. FNADT)
    saisissent parfois "2b267" alors que la commune est enregistrée sous
    "2B267" (départements corses 2A/2B)."""
    if not code_insee:
        return None

    if not COMMUNES:
        for c in Commune.objects.all():
            COMMUNES[c.insee_code.upper()] = c

    return COMMUNES.get(code_insee.upper())


def parse_excel_decimal(value):
    """Convertit une valeur brute de cellule Excel (nombre openpyxl, ou
    texte saisi à la main avec virgule décimale et espaces de séparation
    par milliers, y compris insécables) en `Decimal`. Retourne `None` si la
    valeur est vide ou non convertible."""
    if not value:
        return None
    cleaned = str(value).strip().replace(",", ".").replace(" ", "").replace("\xa0", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


@dataclass
class InvalidRow:
    """Une ligne ignorée par un importeur (cf. `_build_*_subvention`), avec
    le motif regroupable qui a causé son rejet. `field` n'est renseigné que
    pour un champ obligatoire manquant, pour permettre un sous-bilan par
    champ (cf. `summarize_invalid_rows`)."""

    line: int
    reason: str
    field: str | None = None


@dataclass
class InvalidRowsSummary:
    """Un bilan : nombre de lignes concernées par un motif + liste de ces
    lignes."""

    reason: str
    count: int = 0
    lines: list[int] = field(default_factory=list)


def summarize_invalid_rows(invalid_rows: list[InvalidRow]) -> list[InvalidRowsSummary]:
    """Regroupe les lignes invalidées par motif (`reason`, complété du champ
    fautif s'il est renseigné) en un bilan par motif."""
    summaries_by_reason: dict[str, InvalidRowsSummary] = {}
    for invalid_row in invalid_rows:
        reason = invalid_row.reason
        if invalid_row.field:
            reason += f" - {invalid_row.field}"

        summary = summaries_by_reason.setdefault(
            reason, InvalidRowsSummary(reason=reason)
        )
        summary.count += 1
        summary.lines.append(invalid_row.line)
    return list(summaries_by_reason.values())


def log_invalidated_lines(
    logger: logging.Logger,
    invalid_rows: list[InvalidRow],
    hidden_reasons: Iterable[str] = (),
) -> None:
    """Regroupe (cf. `summarize_invalid_rows`) et journalise (info) le bilan
    des lignes invalidées, un message par motif. `hidden_reasons` : motifs à
    ne pas journaliser (ex. lignes hors périmètre par construction plutôt
    que problème de données à corriger — cf. `DSID_SKIPPED_REASON`)."""
    hidden_reasons = set(hidden_reasons)
    for summary in summarize_invalid_rows(invalid_rows):
        if summary.reason in hidden_reasons:
            continue
        logger.info(
            f"    {summary.reason} : {summary.count} ligne(s) — lignes {summary.lines}"
        )


def reset_geo_cache():
    """Vide le cache mémoire de `resolve_departement`/`resolve_commune`. À
    utiliser dans les tests (fixture autouse) : la base est réinitialisée à
    chaque test mais pas ce cache en mémoire, qui référencerait alors des
    objets d'un test précédent."""
    global DEPARTEMENTS, COMMUNES
    DEPARTEMENTS = {}
    COMMUNES = {}
