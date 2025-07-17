import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl_core.tests.factories import CollegueFactory
from gsl_notification.forms import ArreteForm, ArreteSigneForm, ModeleArreteStepTwoForm
from gsl_programmation.tests.factories import ProgrammationProjetFactory

# Arrête


@pytest.mark.django_db
def test_arrete_form_valid():
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory()
    data = {
        "content": {"foo": "bar"},
        "created_by": collegue.id,
        "programmation_projet": programmation_projet.id,
    }
    form = ArreteForm(data)
    assert form.is_valid()


@pytest.mark.django_db
def test_arrete_form_invalid_missing_fields():
    form = ArreteForm({})
    assert not form.is_valid()
    assert "content" in form.errors
    assert "created_by" in form.errors
    assert "programmation_projet" in form.errors


# ArrêteSigneForm


@pytest.mark.django_db
def test_arrete_signe_form_valid():
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory()
    data = {
        "created_by": collegue.id,
        "programmation_projet": programmation_projet.id,
    }
    form = ArreteSigneForm(
        data,
        files={
            "file": SimpleUploadedFile(
                "test.pdf", b"dummy content", content_type="application/pdf"
            )
        },
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_arrete_signe_form_invalid_missing_fields():
    form = ArreteSigneForm({})
    assert not form.is_valid()
    assert "file" in form.errors
    assert "created_by" in form.errors
    assert "programmation_projet" in form.errors


@pytest.mark.parametrize(
    "file_name, content_type, is_valid",
    [
        ("test.pdf", "application/pdf", True),
        ("test.png", "image/png", True),
        ("test.jpg", "image/jpeg", True),
        ("test.jpeg", "image/jpeg", True),
        ("test.txt", "text/plain", False),
    ],
)
@pytest.mark.django_db
def test_arrete_signe_form_accepts_valid_pdf(file_name, content_type, is_valid):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory()
    file = SimpleUploadedFile(file_name, b"dummy content", content_type=content_type)
    form = ArreteSigneForm(
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


@pytest.mark.parametrize(
    "file_size, is_valid", [(20 * 1024 * 1024, True), (21 * 1024 * 1024, False)]
)
@pytest.mark.django_db
def test_arrete_signe_form_rejects_large_file(file_size, is_valid):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory()
    file = SimpleUploadedFile(
        "test.pdf", b"x" * file_size, content_type="application/pdf"
    )
    form = ArreteSigneForm(
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
