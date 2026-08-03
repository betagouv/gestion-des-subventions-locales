from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from gsl_core.tests.factories import CollegueFactory
from gsl_notification.forms import (
    EXPORT_FORMAT_ONE_PDF_ALL,
    AnnexeForm,
    ArreteEtLettreSigneForm,
    ArreteForm,
    GenerateDotationsDocumentsForm,
    GenerateDocumentsStep3Form,
    LettreNotificationForm,
    ModeleDocumentStepTwoForm,
)
from gsl_notification.models import Arrete, LettreNotification, ModeleArrete
from gsl_notification.tests.factories import (
    ArreteFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    ARRETE,
    DOTATION_DETR,
    DOTATION_DSIL,
    LETTRE,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

# GeneratedDocumentForm


@pytest.mark.parametrize(
    "form_class, modele_factory",
    (
        (ArreteForm, ModeleArreteFactory),
        (LettreNotificationForm, ModeleLettreNotificationFactory),
    ),
)
@pytest.mark.parametrize(
    "dotation",
    (DOTATION_DETR, DOTATION_DSIL),
)
@pytest.mark.django_db
def test_arrete_form_valid(form_class, modele_factory, dotation):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet__dotation=dotation
    )
    modele = modele_factory(dotation=dotation)
    data = {
        "content": {"foo": "bar"},
        "created_by": collegue.id,
        "programmation_projet": programmation_projet.id,
        "modele": modele.id,
    }
    form = form_class(data)
    assert form.is_valid()


@pytest.mark.parametrize(
    "form_class",
    (
        ArreteForm,
        LettreNotificationForm,
    ),
)
@pytest.mark.django_db
def test_arrete_form_invalid_missing_fields(form_class):
    form = form_class({})
    assert not form.is_valid()
    assert "content" in form.errors
    assert "created_by" in form.errors
    assert "programmation_projet" in form.errors
    assert "modele" in form.errors


# UploadedDocumentForm


@pytest.mark.parametrize("form_class", (ArreteEtLettreSigneForm, AnnexeForm))
@pytest.mark.django_db
def test_arrete_et_lettre_signe_form_valid(form_class):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory()
    data = {
        "created_by": collegue.id,
        "programmation_projet": programmation_projet.id,
    }
    form = form_class(
        data,
        files={
            "file": SimpleUploadedFile(
                "test.pdf", b"dummy content", content_type="application/pdf"
            )
        },
    )
    assert form.is_valid()


@pytest.mark.parametrize("form_class", (ArreteEtLettreSigneForm, AnnexeForm))
@pytest.mark.django_db
def test_arrete_et_lettre_signe_form_invalid_missing_fields(form_class):
    form = form_class({})
    assert not form.is_valid()
    assert "file" in form.errors
    assert "created_by" in form.errors
    assert "programmation_projet" in form.errors


@pytest.mark.parametrize("form_class", (ArreteEtLettreSigneForm, AnnexeForm))
@pytest.mark.parametrize(
    "file_name, content_type, is_valid",
    [
        ("test.pdf", "application/pdf", True),
        ("test.png", "image/png", True),
        ("test.jpg", "image/jpeg", True),
        ("test.jpeg", "image/jpeg", True),
        ("test.txt", "text/plain", False),
        ("test.pdf", "text/plain", False),
    ],
)
@pytest.mark.django_db
def test_arrete_et_lettre_signe_form_accepts_valid_pdf(
    form_class, file_name, content_type, is_valid
):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory()
    file = SimpleUploadedFile(file_name, b"dummy content", content_type=content_type)
    form = form_class(
        files={"file": file},
        data={
            "created_by": collegue.id,
            "programmation_projet": programmation_projet.id,
        },
    )
    assert form.is_valid() == is_valid
    if not is_valid:
        assert (
            "Seuls les fichiers PDF, PNG ou JPEG sont acceptés."
            in form.errors["file"][0]
        )


@pytest.mark.parametrize("form_class", (ArreteEtLettreSigneForm, AnnexeForm))
@pytest.mark.parametrize(
    "file_size, is_valid", [(20 * 1024 * 1024, True), (21 * 1024 * 1024, False)]
)
@pytest.mark.django_db
def test_arrete_et_lettre_signe_form_rejects_large_file(
    form_class, file_size, is_valid
):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory()
    file = SimpleUploadedFile(
        "test.pdf", b"x" * file_size, content_type="application/pdf"
    )
    form = form_class(
        files={"file": file},
        data={
            "created_by": collegue,
            "programmation_projet": programmation_projet,
        },
    )
    assert form.is_valid() == is_valid
    if not is_valid:
        assert (
            "La taille du fichier ne doit pas dépasser 20 Mo." in form.errors["file"][0]
        )


# Test modele arrêté step 2 (form upload)


class ModeleArreteStepTwoForm(ModeleDocumentStepTwoForm):
    class Meta:
        model = ModeleArrete
        fields = ModeleDocumentStepTwoForm.Meta.fields


def test_modele_arrete_step_2_valid_form_upload():
    form = ModeleArreteStepTwoForm(
        files={
            "logo": SimpleUploadedFile("test.png", b"youpi", content_type="image/png")
        },
        data={
            "logo_alt_text": "texte alternatif du logo",
            "top_right_text": "texte en haut à droite",
        },
    )
    assert form.is_valid(), f"unexpected errors: {form.errors}"


def test_modele_arrete_step_2_rejects_invalid_content_type():
    form = ModeleArreteStepTwoForm(
        files={
            "logo": SimpleUploadedFile(
                "test.png", b"shady", content_type="application/pdf"
            )
        },
        data={
            "logo_alt_text": "texte alternatif du logo",
            "top_right_text": "texte en haut à droite",
        },
    )
    assert not form.is_valid()


def test_modele_arrete_step_2_rejects_invalid_extension():
    form = ModeleArreteStepTwoForm(
        files={
            "logo": SimpleUploadedFile("test.pdf", b"shady", content_type="image/png")
        },
        data={
            "logo_alt_text": "texte alternatif du logo",
            "top_right_text": "texte en haut à droite",
        },
    )
    assert not form.is_valid()


@pytest.mark.parametrize(
    "file_size, is_valid", [(20 * 1024 * 1024, True), (21 * 1024 * 1024, False)]
)
def test_modele_arrete_step_2_rejects_too_large_files(file_size, is_valid):
    form = ModeleArreteStepTwoForm(
        files={
            "logo": SimpleUploadedFile(
                "test.png", b"a" * file_size, content_type="image/png"
            )
        },
        data={
            "logo_alt_text": "texte alternatif du logo",
            "top_right_text": "texte en haut à droite",
        },
    )
    assert form.is_valid() == is_valid, form.errors


@pytest.mark.django_db
def test_generate_documents_step3_form_exposes_with_qr_code():
    user = CollegueFactory()
    field = GenerateDocumentsStep3Form(
        user=user,
        dotation=DOTATION_DETR,
        request=None,
        document_type=ARRETE,
    ).fields["with_qr_code"]
    assert field.required is False
    assert field.initial is True


@pytest.mark.django_db
def test_generate_documents_step3_form_valid_without_qr_field_submitted():
    """An unchecked checkbox sends nothing: the form stays valid (opt-out)."""
    user = CollegueFactory()
    form = GenerateDocumentsStep3Form(
        data={"export_format": EXPORT_FORMAT_ONE_PDF_ALL},
        user=user,
        dotation=DOTATION_DETR,
        request=None,
        document_type=ARRETE,
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["with_qr_code"] is False


# GenerateDotationsDocumentsForm -------------------------------------


def _make_accepted_dotation_projet(dotation, projet=None):
    dp = DotationProjetFactory(
        projet=projet or ProjetFactory(),
        dotation=dotation,
        status=PROJET_STATUS_ACCEPTED,
    )
    return ProgrammationProjetFactory(dotation_projet=dp)


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_only_lists_accepted_dotations():
    projet = ProjetFactory()
    DotationProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_PROCESSING
    )
    _make_accepted_dotation_projet(DOTATION_DETR, projet=projet)
    user = CollegueFactory()

    form = GenerateDotationsDocumentsForm(projet=projet, user=user)

    assert list(form.dotation_fields.keys()) == [DOTATION_DETR]


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_requires_modele_unless_skipped():
    user = CollegueFactory()
    pp = _make_accepted_dotation_projet(DOTATION_DETR)
    projet = pp.dotation_projet.projet
    ModeleArreteFactory(dotation=DOTATION_DETR, perimetre=user.perimetre)
    ModeleLettreNotificationFactory(dotation=DOTATION_DETR, perimetre=user.perimetre)

    form = GenerateDotationsDocumentsForm({}, projet=projet, user=user)

    assert not form.is_valid()
    assert f"modele_arrete_{DOTATION_DETR}" in form.errors
    assert f"modele_lettre_{DOTATION_DETR}" in form.errors


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_forces_skip_when_no_modele():
    user = CollegueFactory()
    pp = _make_accepted_dotation_projet(DOTATION_DETR)
    projet = pp.dotation_projet.projet

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
    pp = _make_accepted_dotation_projet(DOTATION_DETR)
    projet = pp.dotation_projet.projet

    data = {
        f"skip_arrete_{DOTATION_DETR}": "on",
        f"skip_lettre_{DOTATION_DETR}": "on",
    }
    form = GenerateDotationsDocumentsForm(data, projet=projet, user=user)

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_creates_documents():
    user = CollegueFactory()
    pp = _make_accepted_dotation_projet(DOTATION_DETR)
    projet = pp.dotation_projet.projet
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
    pp.refresh_from_db()
    assert pp.arrete.modele == modele_arrete
    assert pp.arrete.created_by == user
    assert pp.lettre.modele == modele_lettre


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_skip_prevents_creation():
    user = CollegueFactory()
    pp = _make_accepted_dotation_projet(DOTATION_DETR)
    projet = pp.dotation_projet.projet
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

    assert Arrete.objects.filter(programmation_projet=pp).exists()
    assert not LettreNotification.objects.filter(programmation_projet=pp).exists()


@pytest.mark.django_db
def test_generate_accepted_dotations_documents_form_overwrites_existing_document():
    user = CollegueFactory()
    pp = _make_accepted_dotation_projet(DOTATION_DETR)
    old_modele = ModeleArreteFactory(dotation=DOTATION_DETR, perimetre=user.perimetre)
    existing = ArreteFactory(programmation_projet=pp, modele=old_modele)
    projet = pp.dotation_projet.projet
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

    assert Arrete.objects.filter(programmation_projet=pp).count() == 1
    pp.refresh_from_db()
    assert pp.arrete.pk != existing.pk
    assert pp.arrete.modele == new_modele


@pytest.mark.django_db
@override_settings(GENERATE_DOCUMENT_SIZE=True)
@patch(
    "gsl_notification.utils.generate_pdf_for_generated_document", return_value=b"PDF"
)
def test_generate_accepted_dotations_documents_form_hide_qr_code_propagates(
    mock_generate_pdf,
):
    user = CollegueFactory()
    pp = _make_accepted_dotation_projet(DOTATION_DETR)
    projet = pp.dotation_projet.projet
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
