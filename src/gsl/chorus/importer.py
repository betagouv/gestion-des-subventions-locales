import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

import openpyxl
from django.db import transaction

from dn.sync.models import Dossier, Dotation

from .models import LIGNE_IDENTITY_FIELDS, SuiviFinancier
from .signals import suivi_financier_imported

COLUMN_HEADERS = {
    "ej": "Nº pce réf",
    "dn": "Axe ministériel 2",
    "domaine_fonctionnel": "Dom. fonc.",
    "montant": "Mont.DT",
    "date": "CB dteComp",
    "date_engagement": "Saisie le",
    "tv": "TV",
    "type_montant": "TypeMtant",
    "poste": "Pos.r",
    "compte_general": "Cpte gén.",
}

DOMAINE_FONCTIONNEL_DOTATION = {
    "0119-01-06": Dotation.DETR,
    "0119-01-07": Dotation.DSIL,
}

# The DN is hand-typed in the "Axe ministériel 2" column in inconsistent formats
# ("DN-30736671", "DS : 15480250", "DS-n°16090518", bare "15345041"…) mixed with
# noise ("CRTE-2022", "DOSSIER PAPIER"…). Valid DS/DN numbers are exactly 8 digits
# (like Dossier.ds_number), so we match an 8-digit run with no digit on either side.
DN_RE = re.compile(r"(?<!\d)\d{8}(?!\d)")

BATCH_SIZE = 2000


class ChorusImportError(Exception):
    pass


@dataclass
class ChorusImportResult:
    imported: int = 0
    matched: int = 0
    duplicate: int = 0
    skipped: int = 0


@transaction.atomic
def import_chorus_file(file):
    """
    Import a Chorus « Journal des pièces » XLSX export into SuiviFinancier.

    `file` is a path or a file-like object.
    """
    known = set(Dossier.objects.values_list("ds_number", flat=True))
    seen = set(SuiviFinancier.objects.values_list(*LIGNE_IDENTITY_FIELDS))
    batch = []
    result = ChorusImportResult()
    for record in iter_records(file):
        ej = str(record["ej"]).strip() if record["ej"] is not None else ""
        montant = parse_montant(record["montant"])
        if not ej or montant is None:
            result.skipped += 1
            continue
        fields = {
            "ej": ej,
            "dn": extract_dn_number(record["dn"]),
            "dotation": DOMAINE_FONCTIONNEL_DOTATION.get(
                str(record["domaine_fonctionnel"] or "").strip(), ""
            ),
            "montant": montant,
            "date_transaction": parse_date(record["date"]),
            "date_engagement": parse_date(record["date_engagement"]),
            "tv": str(record["tv"] or "").strip()[:5],
            "type_montant": str(record["type_montant"] or "").strip()[:10],
            "poste": str(record["poste"] or "").strip()[:10],
            "compte_general": str(record["compte_general"] or "").strip()[:20],
        }
        key = tuple(fields[name] for name in LIGNE_IDENTITY_FIELDS)
        if key in seen:
            result.duplicate += 1
            continue
        seen.add(key)
        batch.append(SuiviFinancier(**fields))
        result.imported += 1
        if fields["dn"] in known:
            result.matched += 1
        if len(batch) >= BATCH_SIZE:
            SuiviFinancier.objects.bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        SuiviFinancier.objects.bulk_create(batch, ignore_conflicts=True)
    suivi_financier_imported.send(sender=SuiviFinancier)
    return result


def iter_records(file):
    """Yield one dict of raw cell values per data row, keyed like COLUMN_HEADERS."""
    workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    sheet = workbook.active
    columns, header_row = locate_columns(sheet)
    for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
        record = {key: row[index] for key, index in columns.items()}
        ej = record["ej"]
        dn = record["dn"]
        if (ej is None or not str(ej).strip()) and (dn is None or not str(dn).strip()):
            continue
        yield record
    workbook.close()


def check_headers(file):
    """Raise ChorusImportError if `file` lacks the expected Chorus headers."""
    workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    try:
        locate_columns(workbook.active)
    finally:
        workbook.close()


def locate_columns(sheet):
    for header_row, row in enumerate(
        sheet.iter_rows(min_row=1, max_row=20, values_only=True), start=1
    ):
        headers = {
            (str(v).strip() if v is not None else ""): i for i, v in enumerate(row)
        }
        columns = {
            key: headers[label]
            for key, label in COLUMN_HEADERS.items()
            if label in headers
        }
        if len(columns) == len(COLUMN_HEADERS):
            return columns, header_row
    missing = ", ".join(COLUMN_HEADERS.values())
    raise ChorusImportError(
        f"En-têtes introuvables dans les 20 premières lignes (attendus : {missing})."
    )


def extract_dn_number(value):
    if not value:
        return None
    match = DN_RE.search(str(value))
    return int(match.group()) if match else None


def parse_montant(value):
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        return None
