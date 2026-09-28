import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl.core.tests.factories import CollegueFactory
from gsl.notification.forms.upload import (
    ManualDocumentAttachForm,
    UploadedDocumentAnalyzeForm,
)
from gsl.notification.models import (
    DocumentImportJob,
    LettreEtArreteSignes,
)
from gsl.notification.tests.factories import (
    LettreEtArreteSignesFactory,
)
from gsl.projet.constants import (
    ANNEXE,
    DOTATION_DETR,
    LETTRE_ET_ARRETE_SIGNES,
    ProjetStatus,
)
from gsl.projet.tests.factories import EnveloppeProjetFactory, ProjetFactory

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
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
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
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )

    key = _parked_pdf()
    form = ManualDocumentAttachForm(
        projet=projet,
        data={"document": f"{LETTRE_ET_ARRETE_SIGNES}-DETR", "key": key},
    )
    assert form.is_valid(), form.errors
    document = form.save(user)

    assert isinstance(document, LettreEtArreteSignes)
    assert document.enveloppe_projet == enveloppe_projet
    assert document.created_by == user
    assert document.file.name.startswith(
        f"{LETTRE_ET_ARRETE_SIGNES}/enveloppe_projet_{enveloppe_projet.id}/"
    )
    assert document.file.read() == b"dummy content"
    assert not default_storage.exists(key)


@pytest.mark.django_db
def test_attach_form_refuses_a_document_already_imported():
    """An already-imported document is offered as a disabled (empty-value)
    choice, so picking it cannot validate."""
    projet = ProjetFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )
    LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)

    form = ManualDocumentAttachForm(
        projet=projet,
        data={"document": f"{LETTRE_ET_ARRETE_SIGNES}-DETR", "key": _parked_pdf()},
    )

    assert not form.is_valid()
    assert "document" in form.errors


@pytest.mark.django_db
def test_attach_form_refuses_a_key_outside_the_temporary_prefix():
    projet = ProjetFactory()
    EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=ProjetStatus.ACCEPTED
    )

    form = ManualDocumentAttachForm(
        projet=projet,
        data={
            "document": f"{LETTRE_ET_ARRETE_SIGNES}-DETR",
            "key": f"{LETTRE_ET_ARRETE_SIGNES}/programmation_projet_1/secret.pdf",
        },
    )

    assert not form.is_valid()
    assert form.non_field_errors() == ["Aucun document à importer."]
