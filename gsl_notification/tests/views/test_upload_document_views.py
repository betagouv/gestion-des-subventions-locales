from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.tests.factories import (
    AnnexeFactory,
    ArreteSigneFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import ANNEXE, ARRETE_ET_LETTRE_SIGNE

pytestmark = pytest.mark.django_db


## FIXTURES


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def programmation_projet(perimetre):
    return ProgrammationProjetFactory(dotation_projet__projet__perimetre=perimetre)


@pytest.fixture
def correct_perimetre_client_with_user_logged(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture
def different_perimetre_client_with_user_logged():
    user = CollegueFactory()
    return ClientWithLoggedUserFactory(user)


### upload-a-document -----------------------------


##### GET
@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNE, ANNEXE))
def test_create_uploaded_document_view_with_not_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": doc_type,
        },
    )
    assert (
        url
        == f"/notification/{programmation_projet.id}/televersement/{doc_type}/creer/"
    )
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNE, ANNEXE))
def test_create_uploaded_document_view_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": doc_type,
        },
    )
    assert (
        url
        == f"/notification/{programmation_projet.id}/televersement/{doc_type}/creer/"
    )
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert "form" in response.context
    assert (
        response.templates[0].name
        == "gsl_notification/uploaded_document/upload_document.html"
    )


##### POST


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNE, ANNEXE))
def test_create_uploaded_document_view_valid_but_with_invalid_user_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
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


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNE, ANNEXE))
def test_create_uploaded_document_view_valid(
    programmation_projet, correct_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
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
    assert response["Location"] == f"/notification/{programmation_projet.id}/documents/"
    if doc_type == ARRETE_ET_LETTRE_SIGNE:
        assert programmation_projet.arrete_signe is not None
        doc = programmation_projet.arrete_signe
    else:
        assert programmation_projet.annexes.count() == 1
        doc = programmation_projet.annexes.first()

    assert f"programmation_projet_{programmation_projet.id}/test" in doc.file.name
    assert doc.created_by == correct_perimetre_client_with_user_logged.user


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNE, ANNEXE))
def test_create_uploaded_document_view_invalid(
    programmation_projet, correct_perimetre_client_with_user_logged, doc_type
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
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


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNE, ANNEXE))
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


@pytest.mark.parametrize(
    "doc_type, factory",
    ((ARRETE_ET_LETTRE_SIGNE, ArreteSigneFactory), (ANNEXE, AnnexeFactory)),
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
    ((ARRETE_ET_LETTRE_SIGNE, ArreteSigneFactory), (ANNEXE, AnnexeFactory)),
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


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNE, ANNEXE))
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
    ((ARRETE_ET_LETTRE_SIGNE, ArreteSigneFactory), (ANNEXE, AnnexeFactory)),
)
def test_uploaded_document_view_url_without_correct_perimetre_and_without_arrete(
    different_perimetre_client_with_user_logged, doc_type, factory
):
    doc = factory()
    url = doc.get_view_url()
    assert url == f"/notification/document-televerse/{doc_type}/{doc.id}/view/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404
