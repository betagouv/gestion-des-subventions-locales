from unittest.mock import patch

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from gsl.projet.constants import (
    ANNEXE,
    ARRETE,
    DOTATION_DETR,
    DOTATION_DSIL,
    LETTRE,
    LETTRE_ET_ARRETE_SIGNES,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl.projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_core.tests.factories import CollegueFactory
from gsl_notification.forms import (
    EXPORT_FORMAT_ONE_PDF_ALL,
    ArreteForm,
    GenerateDocumentsCreateForm,
    GenerateDocumentsFormatForm,
    GenerateDocumentsModeleSelectionForm,
    GenerateDotationsDocumentsForm,
    LettreNotificationForm,
    ManualDocumentAttachForm,
    ModeleDocumentStepTwoForm,
    UploadedDocumentAnalyzeForm,
)
from gsl_notification.models import (
    Arrete,
    DocumentImportJob,
    LettreEtArreteSignes,
    LettreNotification,
    ModeleArrete,
)
from gsl_notification.tests.factories import (
    ArreteFactory,
    LettreEtArreteSignesFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_notification.utils import MENTIONS
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory

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


# Import modal forms


def _pdf(name="test.pdf"):
    return SimpleUploadedFile(name, b"dummy content", content_type="application/pdf")


def _parked_pdf(name="test.pdf"):
    """A file waiting under the temporary prefix, where the analyse step leaves
    one it could not identify."""
    return default_storage.save(DocumentImportJob.temp_s3_key(name), _pdf(name))


def test_analyze_form_valid():
    form = UploadedDocumentAnalyzeForm(data={}, files={"file": _pdf()})
    assert form.is_valid(), form.errors


def test_analyze_form_requires_a_file():
    form = UploadedDocumentAnalyzeForm(data={}, files={})
    assert not form.is_valid()
    assert form.errors["file"] == ["Sélectionnez un document à importer."]


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
def test_analyze_form_accepted_file_types(file_name, content_type, is_valid):
    file = SimpleUploadedFile(file_name, b"dummy content", content_type=content_type)
    form = UploadedDocumentAnalyzeForm(data={}, files={"file": file})

    assert form.is_valid() == is_valid
    if not is_valid:
        assert (
            "Seuls les fichiers PDF, PNG ou JPEG sont acceptés."
            in form.errors["file"][0]
        )


@pytest.mark.parametrize(
    "file_size, is_valid", [(20 * 1024 * 1024, True), (21 * 1024 * 1024, False)]
)
def test_analyze_form_rejects_large_file(file_size, is_valid):
    file = SimpleUploadedFile(
        "test.pdf", b"x" * file_size, content_type="application/pdf"
    )
    form = UploadedDocumentAnalyzeForm(data={}, files={"file": file})

    assert form.is_valid() == is_valid
    if not is_valid:
        assert (
            "La taille du fichier ne doit pas dépasser 20 Mo." in form.errors["file"][0]
        )


@pytest.mark.django_db
def test_attach_form_only_offers_documents_importable_on_the_projet():
    projet = ProjetFactory()
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet, status=ProgrammationProjet.STATUS_ACCEPTED
    )

    form = ManualDocumentAttachForm(projet=projet)

    assert dict(form.fields["document"].choices) == {
        f"{LETTRE_ET_ARRETE_SIGNES}-DETR": "Lettre et arrêté signés DETR",
        f"{ANNEXE}-DETR": "Annexe DETR",
    }


@pytest.mark.django_db
def test_attach_form_saves_the_document_on_the_chosen_dotation():
    user = CollegueFactory()
    projet = ProjetFactory()
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=dotation_projet, status=ProgrammationProjet.STATUS_ACCEPTED
    )

    key = _parked_pdf()
    form = ManualDocumentAttachForm(
        projet=projet,
        data={"document": f"{LETTRE_ET_ARRETE_SIGNES}-DETR", "key": key},
    )
    assert form.is_valid(), form.errors
    document = form.save(user)

    assert isinstance(document, LettreEtArreteSignes)
    assert document.programmation_projet == programmation_projet
    assert document.created_by == user
    assert document.file.name.startswith(
        f"{LETTRE_ET_ARRETE_SIGNES}/programmation_projet_{programmation_projet.id}/"
    )
    assert document.file.read() == b"dummy content"
    assert not default_storage.exists(key)


@pytest.mark.django_db
def test_attach_form_refuses_a_document_already_imported():
    """An already-imported document is offered as a disabled (empty-value)
    choice, so picking it cannot validate."""
    projet = ProjetFactory()
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    programmation_projet = ProgrammationProjetFactory(
        dotation_projet=dotation_projet, status=ProgrammationProjet.STATUS_ACCEPTED
    )
    LettreEtArreteSignesFactory(programmation_projet=programmation_projet)

    form = ManualDocumentAttachForm(
        projet=projet,
        data={"document": f"{LETTRE_ET_ARRETE_SIGNES}-DETR", "key": _parked_pdf()},
    )

    assert not form.is_valid()
    assert "document" in form.errors


@pytest.mark.django_db
def test_attach_form_refuses_a_key_outside_the_temporary_prefix():
    projet = ProjetFactory()
    dotation_projet = DotationProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet, status=ProgrammationProjet.STATUS_ACCEPTED
    )

    form = ManualDocumentAttachForm(
        projet=projet,
        data={
            "document": f"{LETTRE_ET_ARRETE_SIGNES}-DETR",
            "key": f"{LETTRE_ET_ARRETE_SIGNES}/programmation_projet_1/secret.pdf",
        },
    )

    assert not form.is_valid()
    assert form.errors["key"] == ["Requête invalide."]


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
    field = GenerateDocumentsFormatForm(
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
    form = GenerateDocumentsFormatForm(
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


# GenerateDocumentsCreateForm — N+1 queries ------------------------------


def _content_with_every_mention() -> str:
    """A modele body referencing every Mention defined in gsl_notification.utils,
    so replace_mentions_in_html() walks every attribute path it can walk."""
    return "".join(
        f'<span class="mention" data-id="{mention.key}"></span>' for mention in MENTIONS
    )


def _save_documents(programmation_projets, modele) -> int:
    """Runs GenerateDocumentsCreateForm.save() for the given projets and
    returns the number of queries it issued."""
    form = GenerateDocumentsCreateForm(
        user=CollegueFactory(),
        dotation=DOTATION_DETR,
        request=None,
        programmation_projets=ProgrammationProjet.objects.filter(
            pk__in=[pp.pk for pp in programmation_projets]
        ),
    )
    with CaptureQueriesContext(connection) as ctx:
        form.save(
            modeles=[modele],
            overwrite_strategy=GenerateDocumentsModeleSelectionForm.STRATEGY_CONSERVER,
        )
    return len(ctx.captured_queries)


@pytest.mark.django_db
def test_generate_documents_create_form_save_is_not_n_plus_1_on_all_mentions():
    """Regression test: a modele using every possible mention must not add a
    query per projet. replace_mentions_in_html() and _log_doc_action() both
    walk the dotation_projet -> projet -> dossier_ds -> ds_demandeur/perimetre
    chain for every mention, so pps_to_create must eager-load it once for the
    whole batch instead of once per projet."""
    modele = ModeleLettreNotificationFactory(
        dotation=DOTATION_DETR, content=_content_with_every_mention()
    )

    one_pp = ProgrammationProjetFactory.create_batch(
        1, dotation_projet__dotation=DOTATION_DETR
    )
    queries_for_one = _save_documents(one_pp, modele)

    five_pps = ProgrammationProjetFactory.create_batch(
        5, dotation_projet__dotation=DOTATION_DETR
    )
    queries_for_five = _save_documents(five_pps, modele)

    # The only per-projet query left should be the document INSERT itself
    # (one row per projet, GENERATE_DOCUMENT_SIZE=False in tests so no PDF
    # rendering): +4 queries for +4 projets. If any hop in the mention chain
    # weren't eager-loaded, this delta would grow with the batch size instead.
    assert queries_for_five - queries_for_one == 4
