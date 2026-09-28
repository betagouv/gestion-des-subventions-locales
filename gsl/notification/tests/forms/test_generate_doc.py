from unittest.mock import patch

import pytest
from django.test import override_settings

from gsl.core.tests.factories import CollegueFactory, PerimetreRegionalFactory
from gsl.notification.forms.generate_doc import GenerateDotationsDocumentsForm
from gsl.notification.models import (
    Arrete,
    LettreNotification,
)
from gsl.notification.tests.factories import (
    ArreteFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl.projet.constants import (
    ARRETE,
    DOTATION_DETR,
    DOTATION_DSIL,
    LETTRE,
    ProjetStatus,
)
from gsl.projet.tests.factories import EnveloppeProjetFactory, ProjetFactory

# GenerateDotationsDocumentsForm -------------------------------------


def _make_accepted_enveloppe_projet(dotation, projet=None):
    return EnveloppeProjetFactory(
        projet=projet or ProjetFactory(),
        dotation=dotation,
        status=ProjetStatus.ACCEPTED,
    )


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_only_lists_accepted_dotations():
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.PROCESSING
    )
    _make_accepted_enveloppe_projet(DOTATION_DETR, projet=projet)
    user = CollegueFactory()

    form = GenerateDotationsDocumentsForm(projet=projet, user=user)

    assert list(form.dotation_fields.keys()) == [DOTATION_DETR]


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_has_no_detr_field_for_regional_user():
    user = CollegueFactory(perimetre=PerimetreRegionalFactory())
    projet = ProjetFactory()
    _make_accepted_enveloppe_projet(DOTATION_DETR, projet=projet)
    _make_accepted_enveloppe_projet(DOTATION_DSIL, projet=projet)

    data = {
        f"skip_arrete_{DOTATION_DSIL}": "on",
        f"skip_lettre_{DOTATION_DSIL}": "on",
    }
    form = GenerateDotationsDocumentsForm(data, projet=projet, user=user)

    assert form.dotation_fields[DOTATION_DETR]["fields"] == {}
    assert set(form.dotation_fields[DOTATION_DSIL]["fields"]) == {ARRETE, LETTRE}
    assert f"modele_arrete_{DOTATION_DETR}" not in form.fields
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_requires_modele_unless_skipped():
    user = CollegueFactory()
    enveloppe_projet = _make_accepted_enveloppe_projet(DOTATION_DETR)
    projet = enveloppe_projet.projet
    ModeleArreteFactory(dotation=DOTATION_DETR, perimetre=user.perimetre)
    ModeleLettreNotificationFactory(dotation=DOTATION_DETR, perimetre=user.perimetre)

    form = GenerateDotationsDocumentsForm({}, projet=projet, user=user)

    assert not form.is_valid()
    assert f"modele_arrete_{DOTATION_DETR}" in form.errors
    assert f"modele_lettre_{DOTATION_DETR}" in form.errors


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_forces_skip_when_no_modele():
    user = CollegueFactory()
    enveloppe_projet = _make_accepted_enveloppe_projet(DOTATION_DETR)
    projet = enveloppe_projet.projet

    form = GenerateDotationsDocumentsForm({}, projet=projet, user=user)

    fields = form.dotation_fields[DOTATION_DETR]["fields"]
    assert fields[ARRETE]["has_modele"] is False
    assert fields[LETTRE]["has_modele"] is False
    assert form.fields[f"skip_arrete_{DOTATION_DETR}"].disabled
    assert form.fields[f"skip_lettre_{DOTATION_DETR}"].disabled

    assert form.is_valid(), form.errors
    assert form.cleaned_data[f"skip_arrete_{DOTATION_DETR}"] is True
    assert form.cleaned_data[f"skip_lettre_{DOTATION_DETR}"] is True


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_skip_does_not_require_modele():
    user = CollegueFactory()
    enveloppe_projet = _make_accepted_enveloppe_projet(DOTATION_DETR)
    projet = enveloppe_projet.projet

    data = {
        f"skip_arrete_{DOTATION_DETR}": "on",
        f"skip_lettre_{DOTATION_DETR}": "on",
    }
    form = GenerateDotationsDocumentsForm(data, projet=projet, user=user)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_creates_documents():
    user = CollegueFactory()
    enveloppe_projet = _make_accepted_enveloppe_projet(DOTATION_DETR)
    projet = enveloppe_projet.projet
    modele_arrete = ModeleArreteFactory(
        dotation=DOTATION_DETR, perimetre=user.perimetre
    )
    modele_lettre = ModeleLettreNotificationFactory(
        dotation=DOTATION_DETR, perimetre=user.perimetre
    )

    data = {
        f"modele_arrete_{DOTATION_DETR}": modele_arrete.id,
        f"modele_lettre_{DOTATION_DETR}": modele_lettre.id,
    }
    form = GenerateDotationsDocumentsForm(data, projet=projet, user=user)
    assert form.is_valid(), form.errors
    documents = form.save()

    assert len(documents) == 2
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.arrete.modele == modele_arrete
    assert enveloppe_projet.arrete.created_by == user
    assert enveloppe_projet.lettrenotification.modele == modele_lettre


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_skip_prevents_creation():
    user = CollegueFactory()
    enveloppe_projet = _make_accepted_enveloppe_projet(DOTATION_DETR)
    projet = enveloppe_projet.projet
    modele_arrete = ModeleArreteFactory(
        dotation=DOTATION_DETR, perimetre=user.perimetre
    )

    data = {
        f"modele_arrete_{DOTATION_DETR}": modele_arrete.id,
        f"skip_lettre_{DOTATION_DETR}": "on",
    }
    form = GenerateDotationsDocumentsForm(data, projet=projet, user=user)
    assert form.is_valid(), form.errors
    form.save()

    assert Arrete.objects.filter(enveloppe_projet=enveloppe_projet).exists()
    assert not LettreNotification.objects.filter(
        enveloppe_projet=enveloppe_projet
    ).exists()


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_overwrites_existing_document():
    user = CollegueFactory()
    enveloppe_projet = _make_accepted_enveloppe_projet(DOTATION_DETR)
    old_modele = ModeleArreteFactory(dotation=DOTATION_DETR, perimetre=user.perimetre)
    existing = ArreteFactory(enveloppe_projet=enveloppe_projet, modele=old_modele)
    projet = enveloppe_projet.projet
    new_modele = ModeleArreteFactory(dotation=DOTATION_DETR, perimetre=user.perimetre)
    modele_lettre = ModeleLettreNotificationFactory(
        dotation=DOTATION_DETR, perimetre=user.perimetre
    )

    data = {
        f"modele_arrete_{DOTATION_DETR}": new_modele.id,
        f"modele_lettre_{DOTATION_DETR}": modele_lettre.id,
    }
    form = GenerateDotationsDocumentsForm(data, projet=projet, user=user)
    assert form.is_valid(), form.errors
    form.save()

    assert Arrete.objects.filter(enveloppe_projet=enveloppe_projet).count() == 1
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.arrete.pk != existing.pk
    assert enveloppe_projet.arrete.modele == new_modele


@pytest.mark.django_db
@override_settings(GENERATE_DOCUMENT_SIZE=True)
@patch(
    "gsl.notification.utils.generate_pdf_for_generated_document", return_value=b"PDF"
)
def test_generate_accepted_dotations_documents_form_hide_qr_code_propagates(
    mock_generate_pdf,
):
    user = CollegueFactory()
    enveloppe_projet = _make_accepted_enveloppe_projet(DOTATION_DETR)
    projet = enveloppe_projet.projet
    modele_arrete = ModeleArreteFactory(
        dotation=DOTATION_DETR, perimetre=user.perimetre
    )
    modele_lettre = ModeleLettreNotificationFactory(
        dotation=DOTATION_DETR, perimetre=user.perimetre
    )

    data = {
        f"modele_arrete_{DOTATION_DETR}": modele_arrete.id,
        f"modele_lettre_{DOTATION_DETR}": modele_lettre.id,
        "hide_qr_code": "on",
    }
    form = GenerateDotationsDocumentsForm(data, projet=projet, user=user)
    assert form.is_valid(), form.errors
    form.save()

    assert mock_generate_pdf.call_count == 2
    for call in mock_generate_pdf.call_args_list:
        assert call.kwargs["with_qr_code"] is False
