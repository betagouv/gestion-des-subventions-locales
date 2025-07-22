import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl_core.tests.factories import CollegueFactory
from gsl_notification.tests.factories import (
    ArreteFactory,
    ArreteSigneFactory,
    ModeleArreteFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory


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
