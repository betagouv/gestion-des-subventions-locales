import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl.notification.forms.modele import ModeleDocumentStepTwoForm
from gsl.notification.models import (
    ModeleArrete,
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
