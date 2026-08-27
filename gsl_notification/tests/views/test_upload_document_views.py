from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.models import LettreRefusSignee
from gsl_notification.tests.factories import (
    AnnexeFactory,
    LettreEtArreteSignesFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    ANNEXE,
    LETTRE_ET_ARRETE_SIGNES,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DetrProjetFactory, ProjetFactory

LETTRE_REFUS_SIGNEE = LettreRefusSignee.document_type

pytestmark = pytest.mark.django_db


## FIXTURES


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def programmation_projet(perimetre):
    return ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre
    )


@pytest.fixture
def refused_programmation_projet(perimetre):
    return ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__status=PROJET_STATUS_REFUSED,
        status=ProgrammationProjet.STATUS_REFUSED,
    )


@pytest.fixture
def correct_perimetre_client_with_user_logged(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture
def different_perimetre_client_with_user_logged():
    user = CollegueFactory()
    return ClientWithLoggedUserFactory(user)


### choose-uploaded-document-type -----------------------------


def test_choose_uploaded_document_type_displays_correctly(perimetre):
    """Test that the upload document type choice page displays correctly"""
    # Create a user with perimetre
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)

    # Create a projet with an accepted DETR dotation
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dp = DetrProjetFactory(projet=projet, status=PROJET_STATUS_ACCEPTED)
    ProgrammationProjetFactory(dotation_projet=dp)

    # Make GET request to the URL
    url = reverse(
        "gsl_notification:choose-uploaded-document-type",
        kwargs={"projet_id": projet.id},
    )
    response = client.get(url)

    # Check response
    assert response.status_code == 200
    assert "gsl_notification/uploaded_document/choose_upload_document_type.html" in [
        t.name for t in response.templates
    ]


def test_choose_uploaded_document_type_offers_signed_letter_for_refused(perimetre):
    """A refused dotation exposes the signed-letter and annexe imports, not the
    accepted-only ones (lettre et arrêté signés)."""
    user = CollegueFactory(perimetre=perimetre)
    client = ClientWithLoggedUserFactory(user)

    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    dp = DetrProjetFactory(projet=projet, status=PROJET_STATUS_REFUSED)
    ProgrammationProjetFactory(
        dotation_projet=dp, status=ProgrammationProjet.STATUS_REFUSED
    )

    url = reverse(
        "gsl_notification:choose-uploaded-document-type",
        kwargs={"projet_id": projet.id},
    )
    response = client.get(url)

    assert response.status_code == 200
    choices = dict(response.context["form"].fields["document"].choices)
    assert choices == {
        f"{LETTRE_REFUS_SIGNEE}-DETR": "Lettre de refus signée DETR",
        f"{ANNEXE}-DETR": "Annexe DETR",
    }


### upload-a-document -----------------------------


##### GET
@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_create_uploaded_document_view_with_not_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged, doc_type
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": doc_type,
        },
    )
    assert (
        url == f"/notification/{projet.id}/televersement/{dotation}/{doc_type}/creer/"
    )
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_create_uploaded_document_view_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged, doc_type
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": doc_type,
        },
    )
    assert (
        url == f"/notification/{projet.id}/televersement/{dotation}/{doc_type}/creer/"
    )
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert "form" in response.context
    assert (
        response.templates[0].name
        == "gsl_notification/uploaded_document/upload_document.html"
    )


##### POST


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_create_uploaded_document_view_valid_but_with_invalid_user_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged, doc_type
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": doc_type,
        },
    )
    file = SimpleUploadedFile("test.pdf", b"dummy", content_type="application/pdf")
    data = {
        "file": file,
        "created_by": different_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
    }
    response = different_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 404


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_create_uploaded_document_view_valid(
    programmation_projet, correct_perimetre_client_with_user_logged, doc_type
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": doc_type,
        },
    )
    file = SimpleUploadedFile("test.pdf", b"dummy", content_type="application/pdf")
    data = {
        "file": file,
        "created_by": correct_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 302
    assert response["Location"] == f"/notification/{projet.id}/documents/"
    if doc_type == LETTRE_ET_ARRETE_SIGNES:
        assert programmation_projet.lettre_et_arrete_signes is not None
        doc = programmation_projet.lettre_et_arrete_signes
    else:
        assert programmation_projet.annexes.count() == 1
        doc = programmation_projet.annexes.first()

    assert f"programmation_projet_{programmation_projet.id}/test" in doc.file.name
    assert doc.created_by == correct_perimetre_client_with_user_logged.user


def test_create_lettre_refus_signee_valid(
    refused_programmation_projet, correct_perimetre_client_with_user_logged
):
    programmation_projet = refused_programmation_projet
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": LETTRE_REFUS_SIGNEE,
        },
    )
    file = SimpleUploadedFile("test.pdf", b"dummy", content_type="application/pdf")
    data = {
        "file": file,
        "created_by": correct_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 302
    assert response["Location"] == f"/notification/{projet.id}/documents/"
    doc = programmation_projet.lettre_refus_signee
    assert doc is not None
    assert f"programmation_projet_{programmation_projet.id}/test" in doc.file.name
    assert doc.created_by == correct_perimetre_client_with_user_logged.user


def test_create_uploaded_document_view_rejects_document_type_status_mismatch(
    refused_programmation_projet, correct_perimetre_client_with_user_logged
):
    """A signed-letter type on an accepted dotation (or vice-versa) is a 400."""
    programmation_projet = refused_programmation_projet
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    # lettre_et_arrete_signes only applies to accepted dotations.
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": LETTRE_ET_ARRETE_SIGNES,
        },
    )
    file = SimpleUploadedFile("test.pdf", b"dummy", content_type="application/pdf")
    data = {
        "file": file,
        "created_by": correct_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 400
    assert "ne peut pas être importé" in response.content.decode()


def test_create_uploaded_document_view_rejects_refusal_letter_on_accepted(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    """Reverse direction: a refusal-letter type on an accepted dotation is a 400."""
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": LETTRE_REFUS_SIGNEE,
        },
    )
    file = SimpleUploadedFile("test.pdf", b"dummy", content_type="application/pdf")
    data = {
        "file": file,
        "created_by": correct_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 400


def test_create_uploaded_document_view_unknown_document_type_is_404(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    """An unknown document_type on a valid programmation is a 404."""
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": "does_not_exist",
        },
    )
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_create_uploaded_document_view_invalid(
    programmation_projet, correct_perimetre_client_with_user_logged, doc_type
):
    projet = programmation_projet.dotation_projet.projet
    dotation = programmation_projet.enveloppe.dotation
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "projet_id": projet.id,
            "dotation": dotation,
            "document_type": doc_type,
        },
    )
    response = correct_perimetre_client_with_user_logged.post(url, {})
    assert response.status_code == 200
    assert response.context["form"].errors == {
        "file": ["Ce champ est obligatoire."],
        "created_by": ["Ce champ est obligatoire."],
        "programmation_projet": ["Ce champ est obligatoire."],
    }
    assert (
        response.templates[0].name
        == "gsl_notification/uploaded_document/upload_document.html"
    )


### uploaded-document-download


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_uploaded_document_download_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:uploaded-document-download",
        kwargs={"document_type": doc_type, "document_id": 1000},
    )
    assert url == f"/notification/document-televerse/{doc_type}/1000/download/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


@override_settings(BYPASS_ANTIVIRUS=True)
@pytest.mark.parametrize(
    "doc_type, factory",
    ((LETTRE_ET_ARRETE_SIGNES, LettreEtArreteSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_uploaded_document_download_url_with_correct_perimetre_and_with_arrete(
    correct_perimetre_client_with_user_logged, programmation_projet, doc_type, factory
):
    doc = factory(programmation_projet=programmation_projet)
    url = doc.get_download_url()
    assert url == f"/notification/document-televerse/{doc_type}/{doc.id}/download/"

    # Mock boto3.client().get_object
    with patch("boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.iter_chunks.return_value = [b"dummy data"]
        mock_s3.get_object.return_value = {
            "Body": mock_body,
            "ContentType": "application/pdf",
        }
        mock_boto_client.return_value = mock_s3

        response = correct_perimetre_client_with_user_logged.get(url)
        assert response.status_code == 200


@pytest.mark.parametrize(
    "doc_type, factory",
    ((LETTRE_ET_ARRETE_SIGNES, LettreEtArreteSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_uploaded_document_download_url_without_correct_perimetre_and_without_arrete(
    different_perimetre_client_with_user_logged, doc_type, factory
):
    doc = factory()
    url = doc.get_download_url()
    assert url == f"/notification/document-televerse/{doc_type}/{doc.id}/download/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


### uploaded-document-view


@pytest.mark.parametrize("doc_type", (LETTRE_ET_ARRETE_SIGNES, ANNEXE))
def test_uploaded_document_view_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:uploaded-document-view",
        kwargs={"document_type": doc_type, "document_id": 1000},
    )
    assert url == f"/notification/document-televerse/{doc_type}/1000/view/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "doc_type, factory",
    ((LETTRE_ET_ARRETE_SIGNES, LettreEtArreteSignesFactory), (ANNEXE, AnnexeFactory)),
)
def test_uploaded_document_view_url_without_correct_perimetre_and_without_arrete(
    different_perimetre_client_with_user_logged, doc_type, factory
):
    doc = factory()
    url = doc.get_view_url()
    assert url == f"/notification/document-televerse/{doc_type}/{doc.id}/view/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404
