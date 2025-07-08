from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.tests.factories import ArreteFactory, ArreteSigneFactory
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_simulation.tests.factories import SimulationProjetFactory

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


## TESTS
pytestmark = pytest.mark.django_db


### get-arrete


def test_get_documents_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    simu = SimulationProjetFactory(dotation_projet=programmation_projet.dotation_projet)
    url = reverse(
        "notification:documents-in-simulation",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "simulation_projet_id": simu.id,
        },
    )
    assert (
        url == f"/notification/{programmation_projet.id}/documents/simulation/{simu.id}"
    )
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    # assert template is correct
    # check context is correct


@pytest.mark.skip(reason="Non implémenté")
def test_create_arrete_url_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:create-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/creer-arrete/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200


def test_modify_arrete_url_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    ArreteFactory(
        programmation_projet=programmation_projet, content="<p>Contenu de l’arrêté</p>"
    )
    url = reverse(
        "notification:modifier-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/modifier-arrete/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert response.context["arrete_initial_content"] == "<p>Contenu de l’arrêté</p>"


@pytest.mark.skip(reason="Non implémenté")
def test_create_arrete_url_with_correct_perimetre_and_with_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    ArreteSigneFactory(programmation_projet=programmation_projet)
    url = reverse(
        "notification:create-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/creer-arrete/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 302
    assert (
        response["Location"] == f"/notification/{programmation_projet.id}/arrete-signe/"
    )


@pytest.mark.parametrize(
    "with_arrete",
    [
        True,
        False,
    ],
)
def test_create_arrete_url_without_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged, with_arrete
):
    if with_arrete:
        ArreteSigneFactory(programmation_projet=programmation_projet)

    url = reverse(
        "notification:create-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/creer-arrete/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


##### POST


@pytest.mark.skip(reason="Redirection vers la vue source non implémentée")
def test_change_arrete_view_valid(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    arrete = ArreteFactory(
        programmation_projet=programmation_projet, content="<p>Ancien contenu</p>"
    )
    url = reverse(
        "notification:modifier-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    data = {
        "created_by": correct_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
        "content": "<p>Le contenu</p>",
    }
    response = correct_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 302
    assert (
        response["Location"] == f"/notification/{programmation_projet.id}/arrete-signe/"
    )
    arrete.refresh_from_db()
    assert arrete.content == "<p>Le contenu</p>"


def test_change_arrete_view_invalid(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    ArreteFactory(
        programmation_projet=programmation_projet, content="<p>Ancien contenu</p>"
    )

    url = reverse(
        "notification:modifier-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    response = correct_perimetre_client_with_user_logged.post(url, {})
    assert response.status_code == 200
    assert response.context["arrete_form"].errors == {
        "created_by": ["Ce champ est obligatoire."],
        "programmation_projet": ["Ce champ est obligatoire."],
        "content": ["Ce champ est obligatoire."],
    }


### arrete-download


def test_arrete_download_url_with_correct_perimetre(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("notification:arrete-download", kwargs={"arrete_id": arrete.id})
    assert url == f"/notification/arrete/{arrete.id}/download/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "attachment;filename=" in response["Content-Disposition"]


def test_arrete_download_url_with_wrong_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("notification:arrete-download", kwargs={"arrete_id": arrete.id})
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


# ArreteSigne

### create-arrete-signe

##### POST


@pytest.mark.skip(reason="Redirection vers la source non implémentée")
def test_create_arrete_signe_view_valid(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:create-arrete-signe",
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


# def test_create_arrete_signe_view_invalid(
#     programmation_projet, correct_perimetre_client_with_user_logged
# ):
#     url = reverse(
#         "notification:create-arrete-signe",
#         kwargs={"programmation_projet_id": programmation_projet.id},
#     )
#     response = correct_perimetre_client_with_user_logged.post(url, {})
#     assert response.status_code == 200
#     assert response.context["arrete_signe_form"].errors == {
#         "file": ["Ce champ est obligatoire."],
#         "created_by": ["Ce champ est obligatoire."],
#         "programmation_projet": ["Ce champ est obligatoire."],
#     }


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
    url = arrete_signe.get_absolute_url()
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
        assert response["Content-Type"] == "application/pdf"


def test_arrete_signe_download_url_without_correct_perimetre_and_without_arrete(
    arrete_signe, different_perimetre_client_with_user_logged
):
    url = arrete_signe.get_absolute_url()
    assert url == f"/notification/arrete-signe/{arrete_signe.id}/download/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404
