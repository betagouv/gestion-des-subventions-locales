import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from gsl_core.tests.factories import CollegueFactory
from gsl_notification.tests.factories import ArreteSigneFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory


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
    assert arrete.name == "test_file.pdf"
    assert arrete.type == "pdf"
    assert arrete.size == len(file_content)
    assert arrete.created_at is not None
