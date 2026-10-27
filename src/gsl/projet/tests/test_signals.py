import pytest
from django.core.management import call_command

from dn.sync.models import Dotation
from gsl.chorus.tests.test_extract_from_chorus import DETR_LINE, write_chorus_xlsx

from .factories import EnveloppeProjetFactory

EJ_LINE = {**DETR_LINE, "dn": "DN-28281965", "tv": "51"}
PAIEMENT_LINE = {**EJ_LINE, "ej": "1000123456", "tv": "57", "type_montant": "0250"}


@pytest.fixture
def enveloppe_projet():
    return EnveloppeProjetFactory(
        dotation=Dotation.DETR, projet__dossier_ds__ds_number=28281965
    )


@pytest.mark.django_db
def test_chorus_import_fills_the_single_ej(tmp_path, enveloppe_projet):
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [EJ_LINE, PAIEMENT_LINE])

    call_command("extract_from_chorus", path)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.ej == "2105003612"


@pytest.mark.django_db
def test_chorus_import_leaves_ej_empty_when_several(tmp_path, enveloppe_projet):
    other_ej_line = {**EJ_LINE, "ej": "2105009999"}
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [EJ_LINE, other_ej_line])

    call_command("extract_from_chorus", path)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.ej == ""


@pytest.mark.django_db
def test_chorus_import_keeps_an_existing_ej(tmp_path, enveloppe_projet):
    enveloppe_projet.ej = "2105000001"
    enveloppe_projet.save()
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [EJ_LINE])

    call_command("extract_from_chorus", path)

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.ej == "2105000001"


@pytest.mark.django_db
def test_chorus_import_only_fills_the_matching_dotation(tmp_path):
    dsil = EnveloppeProjetFactory(
        dotation=Dotation.DSIL, projet__dossier_ds__ds_number=28281965
    )
    path = write_chorus_xlsx(tmp_path / "chorus.xlsx", [EJ_LINE])

    call_command("extract_from_chorus", path)

    dsil.refresh_from_db()
    assert dsil.ej == ""
