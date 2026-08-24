from datetime import date, datetime
from decimal import Decimal

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from gsl_chorus.management.commands.extract_from_chorus import (
    COLUMN_HEADERS,
    extract_dn_number,
    parse_date,
    parse_montant,
)
from gsl_chorus.models import SuiviFinancier
from gsl_demarches_simplifiees.tests.factories import DossierFactory

DETR_LINE = {
    "ej": "2105003612",
    "dn": "DN-28281965",
    "domaine_fonctionnel": "0119-01-06",
    "montant": "9 500,00",
    "date": "03.08.2026",
    "date_engagement": "15.06.2026",
    "tv": "65",
    "type_montant": "0100",
    "poste": "1",
    "compte_general": "6552100000",
}


def write_chorus_xlsx(path, records, preamble_rows=0):
    """Build a minimal Chorus-like XLSX at `path` from a list of record dicts."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    keys = list(COLUMN_HEADERS)
    for _ in range(preamble_rows):
        sheet.append(["préambule"])
    sheet.append([COLUMN_HEADERS[key] for key in keys])
    for record in records:
        sheet.append([record.get(key) for key in keys])
    workbook.save(path)
    return str(path)


# --- pure helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("9 500,00", Decimal("9500.00")),
        ("\xa01 234,50", Decimal("1234.50")),
        ("-35 899,73", Decimal("-35899.73")),
        (9500, Decimal("9500")),
        (Decimal("42.5"), Decimal("42.5")),
        (None, None),
        ("", None),
        ("   ", None),
        ("abc", None),
    ],
)
def test_parse_montant(value, expected):
    assert parse_montant(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("03.08.2026", date(2026, 8, 3)),
        (datetime(2026, 6, 15, 10, 30), date(2026, 6, 15)),
        ("", None),
        ("2026-08-03", None),
        (None, None),
    ],
)
def test_parse_date(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("DN-28281965", 28281965),
        ("DS : 15480250", 15480250),
        ("28355050-28281965", 28355050),  # first 8-digit run wins
        ("CRTE-2022", None),  # too short
        ("123456789", None),  # 9 digits: no clean 8-digit run
        ("DOSSIER PAPIER", None),
        (None, None),
        ("", None),
    ],
)
def test_extract_dn_number(value, expected):
    assert extract_dn_number(value) == expected


# --- import command ---------------------------------------------------------


@pytest.mark.django_db
def test_import_creates_ligne_with_parsed_fields(tmp_path):
    DossierFactory(ds_number=28281965)
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE])

    call_command("extract_from_chorus", path)

    ligne = SuiviFinancier.objects.get()
    assert ligne.ej == "2105003612"
    assert ligne.dn == 28281965
    assert ligne.dotation == "DETR"
    assert ligne.montant == Decimal("9500.00")
    assert ligne.date_transaction == date(2026, 8, 3)
    assert ligne.date_engagement == date(2026, 6, 15)
    assert ligne.tv == "65"
    assert ligne.type_montant == "0100"
    assert ligne.poste == "1"
    assert ligne.compte_general == "6552100000"


@pytest.mark.django_db
def test_dsil_and_unknown_domaine_fonctionnel(tmp_path):
    dsil = {**DETR_LINE, "ej": "2105000001", "domaine_fonctionnel": "0119-01-07"}
    other = {**DETR_LINE, "ej": "2105000002", "domaine_fonctionnel": "0119-99-99"}
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [dsil, other])

    call_command("extract_from_chorus", path)

    assert SuiviFinancier.objects.get(ej="2105000001").dotation == "DSIL"
    assert SuiviFinancier.objects.get(ej="2105000002").dotation == ""


@pytest.mark.django_db
def test_rows_without_ej_or_montant_are_skipped(tmp_path):
    no_ej = {**DETR_LINE, "ej": "", "dn": "DN-28281965"}
    no_montant = {**DETR_LINE, "ej": "2105000009", "montant": ""}
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE, no_ej, no_montant])

    call_command("extract_from_chorus", path)

    assert SuiviFinancier.objects.count() == 1
    assert SuiviFinancier.objects.get().ej == "2105003612"


@pytest.mark.django_db
def test_duplicate_rows_in_one_file_are_deduped(tmp_path):
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE, dict(DETR_LINE)])

    call_command("extract_from_chorus", path)

    assert SuiviFinancier.objects.count() == 1


@pytest.mark.django_db
def test_reimport_is_idempotent(tmp_path):
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE])

    call_command("extract_from_chorus", path)
    call_command("extract_from_chorus", path)

    assert SuiviFinancier.objects.count() == 1


@pytest.mark.django_db
def test_partial_import_is_additive(tmp_path):
    line_a = DETR_LINE
    line_b = {**DETR_LINE, "ej": "2105000002", "montant": "1 000,00"}
    line_c = {**DETR_LINE, "ej": "2105000003", "montant": "2 000,00"}

    full = write_chorus_xlsx(tmp_path / "full.xlsx", [line_a, line_b])
    partial = write_chorus_xlsx(tmp_path / "partial.xlsx", [line_b, line_c])

    call_command("extract_from_chorus", full)
    assert SuiviFinancier.objects.count() == 2

    # line_b overlaps (skipped), line_c is new.
    call_command("extract_from_chorus", partial)
    assert SuiviFinancier.objects.count() == 3
    assert set(SuiviFinancier.objects.values_list("ej", flat=True)) == {
        "2105003612",
        "2105000002",
        "2105000003",
    }


@pytest.mark.django_db
def test_header_located_after_preamble_rows(tmp_path):
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [DETR_LINE], preamble_rows=3)

    call_command("extract_from_chorus", path)

    assert SuiviFinancier.objects.count() == 1


@pytest.mark.django_db
def test_missing_headers_raise(tmp_path):
    workbook = openpyxl.Workbook()
    workbook.active.append(["foo", "bar"])
    path = tmp_path / "bad.xlsx"
    workbook.save(path)

    with pytest.raises(CommandError):
        call_command("extract_from_chorus", str(path))
