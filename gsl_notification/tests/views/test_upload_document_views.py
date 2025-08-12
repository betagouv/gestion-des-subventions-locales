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
    ArreteSigneFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory

pytestmark = pytest.mark.django_db


## FIXTURES


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def programmation_projet(perimetre):
    return ProgrammationProjetFactory(dotation_projet__projet__perimetre=perimetre)


@pytest.fixture
def arrete_signe(programmation_projet):
    return ArreteSigneFactory(programmation_projet=programmation_projet)


@pytest.fixture
def correct_perimetre_client_with_user_logged(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


@pytest.fixture
def different_perimetre_client_with_user_logged():
    user = CollegueFactory()
    return ClientWithLoggedUserFactory(user)


# ArreteSigne

### upload-a-document -----------------------------


##### GET
def test_create_arrete_signe_view_with_not_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/creer-arrete-signe/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_create_arrete_signe_view_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/creer-arrete-signe/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert "arrete_signe_form" in response.context
    assert response.templates[0].name == "gsl_notification/upload_arrete_signe.html"


##### POST


def test_create_arrete_signe_view_valid_but_with_invalid_user_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    file = SimpleUploadedFile("test.pdf", b"dummy", content_type="application/pdf")
    data = {
        "file": file,
        "created_by": different_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
    }
    response = different_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 404


def test_create_arrete_signe_view_valid(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={"programmation_projet_id": programmation_projet.id},
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
    assert programmation_projet.arrete_signe is not None
    assert (
        f"programmation_projet_{programmation_projet.id}/test"
        in programmation_projet.arrete_signe.file.name
    )
    assert (
        programmation_projet.arrete_signe.created_by
        == correct_perimetre_client_with_user_logged.user
    )


def test_create_arrete_signe_view_invalid(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:upload-a-document",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    response = correct_perimetre_client_with_user_logged.post(url, {})
    assert response.status_code == 200
    assert response.context["arrete_signe_form"].errors == {
        "file": ["Ce champ est obligatoire."],
        "created_by": ["Ce champ est obligatoire."],
        "programmation_projet": ["Ce champ est obligatoire."],
    }
    assert response.templates[0].name == "gsl_notification/upload_arrete_signe.html"


### arrete-signe-download


def test_arrete_signe_download_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged,
):
    url = reverse(
        "notification:arrete-signe-download",
        kwargs={"arrete_signe_id": 1000},
    )
    assert url == "/notification/arrete-signe/1000/download/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_arrete_signe_download_url_with_correct_perimetre_and_with_arrete(
    arrete_signe, correct_perimetre_client_with_user_logged
):
    url = arrete_signe.get_download_url()
    assert url == f"/notification/arrete-signe/{arrete_signe.id}/download/"

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


def test_arrete_signe_download_url_without_correct_perimetre_and_without_arrete(
    arrete_signe, different_perimetre_client_with_user_logged
):
    url = arrete_signe.get_download_url()
    assert url == f"/notification/arrete-signe/{arrete_signe.id}/download/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


### arrete-signe-view


def test_arrete_signe_view_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged,
):
    url = reverse(
        "notification:arrete-signe-view",
        kwargs={"arrete_signe_id": 1000},
    )
    assert url == "/notification/arrete-signe/1000/view/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_arrete_signe_view_url_without_correct_perimetre_and_without_arrete(
    arrete_signe, different_perimetre_client_with_user_logged
):
    url = arrete_signe.get_view_url()
    assert url == f"/notification/arrete-signe/{arrete_signe.id}/view/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404
