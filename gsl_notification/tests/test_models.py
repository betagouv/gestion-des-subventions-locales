import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl_core.tests.factories import CollegueFactory, PerimetreDepartementalFactory
from gsl_notification.models import ModeleArrete
from gsl_notification.tests.factories import (
    ArreteFactory,
    ArreteSigneFactory,
    ModeleArreteFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR


@pytest.mark.django_db
def test_arrete_properties():
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    modele = ModeleArreteFactory()

    file_content = {"key": "value"}
    arrete = ArreteFactory(
        created_by=collegue,
        programmation_projet=programmation_projet,
        content=file_content,
        modele=modele,
    )

    assert str(arrete) == f"Arrêté #{arrete.id}"
    assert arrete.content == file_content
    assert arrete.created_by == collegue
    assert arrete.created_at is not None
    assert arrete.updated_at is not None
    assert arrete.programmation_projet == programmation_projet
    assert arrete.modele == modele


@pytest.mark.django_db
def test_arrete_signe_properties():
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )

    file_content = b"dummy content"
    file = SimpleUploadedFile(
        "arrete/test_file.pdf", file_content, content_type="application/pdf"
    )

    arrete = ArreteSigneFactory(
        file=file, created_by=collegue, programmation_projet=programmation_projet
    )

    assert str(arrete) == f"Arrêté signé #{arrete.id} "
    assert arrete.name.startswith(
        "test_file"
    )  # Filename can be changed with a suffix to avoid conflicts
    assert arrete.type == "pdf"
    assert arrete.size == len(file_content)
    assert arrete.created_at is not None
    assert arrete.created_by is collegue
    assert arrete.programmation_projet == programmation_projet


@pytest.mark.django_db
def test_modele_arrete_properties():
    collegue = CollegueFactory()
    file_content = {"key": "value"}
    perimetre = collegue.perimetre
    modele = ModeleArreteFactory(
        created_by=collegue, content=file_content, perimetre=perimetre
    )

    assert str(modele) == f"Modèle d’arrêté {modele.id} - {modele.name}"
    assert modele.content == file_content
    assert modele.created_by == collegue
    assert modele.created_at is not None
    assert modele.updated_at is not None
    assert modele.perimetre == perimetre


@pytest.mark.django_db
def test_two_models_have_different_logos():
    updated_logo = SimpleUploadedFile("my_logo.png", b"logo content", "image/png")

    form_data = {
        "name": "Nom du modèle",
        "description": "Description du modèle",
        "perimetre": PerimetreDepartementalFactory(),
        "dotation": DOTATION_DETR,
        "logo": updated_logo,
        "logo_alt_text": "texte alternatif",
        "top_right_text": "Texte en haut à droite",
        "content": "<p>Contenu</p>",
        "created_by": CollegueFactory(),
    }

    first_modele = ModeleArrete(**form_data)
    first_modele.save()
    second_modele = ModeleArrete(**form_data)
    second_modele.save()

    assert first_modele.id != second_modele.id
    assert first_modele.name == second_modele.name
    assert first_modele.logo.name != second_modele.logo.name
    assert "my_logo" in first_modele.logo.name
    assert "my_logo" in second_modele.logo.name
