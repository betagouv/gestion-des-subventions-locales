import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl_notification.forms import ArreteSigneForm


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
    file = SimpleUploadedFile(file_name, b"dummy content", content_type=content_type)
    form = ArreteSigneForm(files={"file": file})
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
    file = SimpleUploadedFile(
        "test.pdf", b"x" * file_size, content_type="application/pdf"
    )
    form = ArreteSigneForm(files={"file": file})
    assert form.is_valid() == is_valid
    if not is_valid:
        assert (
            "La taille du fichier ne doit pas dépasser 20 Mo." in form.errors["file"][0]
        )
