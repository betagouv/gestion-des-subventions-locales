import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl_core.tests.factories import CollegueFactory, PerimetreDepartementalFactory
from gsl_notification.models import ModeleArrete
from gsl_notification.tests.factories import (
    ArreteFactory,
    ArreteSigneFactory,
    LettreNotificationFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import ARRETE, DOTATION_DETR, LETTRE


@pytest.mark.parametrize(
    "type, modele_factory, factory",
    (
        (ARRETE, ModeleArreteFactory, ArreteFactory),
        (
            LETTRE,
            ModeleLettreNotificationFactory,
            LettreNotificationFactory,
        ),
    ),
)
@pytest.mark.django_db
def test_arrete_properties(type, modele_factory, factory):
    collegue = CollegueFactory()
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED
    )
    modele = modele_factory()

    file_content = {"key": "value"}
    arrete = factory(
        created_by=collegue,
        programmation_projet=programmation_projet,
        content=file_content,
        modele=modele,
    )

    if type == ARRETE:
        assert str(arrete) == f"Arrêté #{arrete.id}"
    else:
        assert str(arrete) == f"Lettre de notification #{arrete.id}"

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
    assert arrete.file_type == "pdf"
    assert arrete.size == len(file_content)
    assert arrete.created_at is not None
    assert arrete.created_by is collegue
    assert arrete.programmation_projet == programmation_projet


@pytest.mark.parametrize(
    "factory", (ModeleArreteFactory, ModeleLettreNotificationFactory)
)
@pytest.mark.django_db
def test_modele_properties(factory):
    collegue = CollegueFactory()
    file_content = {"key": "value"}
    perimetre = collegue.perimetre
    modele = factory(created_by=collegue, content=file_content, perimetre=perimetre)

    if factory == ModeleArreteFactory:
        assert str(modele) == f"Modèle d’arrêté {modele.id} - {modele.name}"
    else:
        assert (
            str(modele)
            == f"Modèle de lettre de notification {modele.id} - {modele.name}"
        )

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
