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


### documents -----------------------------------


def test_get_documents_with_not_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:documents",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
        },
    )
    assert url == f"/notification/{programmation_projet.id}/documents/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_get_documents_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:documents",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
        },
    )
    assert url == f"/notification/{programmation_projet.id}/documents/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/tab_simulation_projet/tab_notifications.html"
    )


### create-arrete -----------------------------------


@pytest.mark.skip(reason="Remove it ?")
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


@pytest.mark.skip(reason="Remove it ?")
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


### modifier-arrete -----------------------------------

##### GET


def test_modify_arrete_url_with_not_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged
):
    ArreteFactory(
        programmation_projet=programmation_projet, content="<p>Contenu de l’arrêté</p>"
    )
    url = reverse(
        "notification:modifier-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/modifier-arrete/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


####### Without an existing arrete


def test_modify_arrete_url_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:modifier-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/modifier-arrete/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert response.context["arrete_initial_content"] == ""
    assert response.context["page_title"] == "Création de l'arrêté"
    assert response.templates[0].name == "gsl_notification/change_arrete.html"


####### With an existing arrete


def test_modify_arrete_url_with_correct_perimetre_and_with_arrete(
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
    assert response.context["page_title"] == "Modification de l'arrêté"
    assert response.templates[0].name == "gsl_notification/change_arrete.html"


##### POST


def test_change_arrete_view_valid_but_with_wrong_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged
):
    assert not hasattr(programmation_projet, "arrete")
    url = reverse(
        "notification:modifier-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    data = {
        "created_by": different_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
        "content": "<p>Le contenu</p>",
    }
    response = different_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 404
    assert not hasattr(programmation_projet, "arrete")


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
    assert response["Location"] == f"/notification/{programmation_projet.id}/documents/"
    arrete.refresh_from_db()
    assert arrete.content == "<p>Le contenu</p>"
    assert arrete.created_by == correct_perimetre_client_with_user_logged.user
    assert arrete.programmation_projet == programmation_projet


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
    assert response.templates[0].name == "gsl_notification/change_arrete.html"


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


def test_arrete_download_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged,
):
    url = reverse("notification:arrete-download", kwargs={"arrete_id": 1000})
    assert url == "/notification/arrete/1000/download/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_arrete_download_url_with_wrong_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("notification:arrete-download", kwargs={"arrete_id": arrete.id})
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


# ArreteSigne

### create-arrete-signe -----------------------------------


##### GET
def test_create_arrete_signe_view_with_not_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:create-arrete-signe",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/creer-arrete-signe/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_create_arrete_signe_view_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:create-arrete-signe",
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
        "notification:create-arrete-signe",
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
        "notification:create-arrete-signe",
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


### delete_arrete --------------------------------


def test_delete_arrete_with_correct_perimetre(
    correct_perimetre_client_with_user_logged, programmation_projet
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("gsl_notification:delete-arrete", args=[arrete.id])

    assert hasattr(programmation_projet, "arrete")

    response = correct_perimetre_client_with_user_logged.post(url)

    expected_redirect_url = reverse(
        "gsl_notification:documents", args=[programmation_projet.id]
    )
    assert response.status_code == 302
    assert response.url == expected_redirect_url

    programmation_projet.refresh_from_db()
    assert not hasattr(programmation_projet, "arrete")


def test_delete_arrete_with_incorrect_perimetre(
    different_perimetre_client_with_user_logged, programmation_projet
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("gsl_notification:delete-arrete", args=[arrete.id])

    response = different_perimetre_client_with_user_logged.post(url)
    assert response.status_code == 404


def test_delete_arrete_with_get_method_not_allowed(
    correct_perimetre_client_with_user_logged, programmation_projet
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("gsl_notification:delete-arrete", args=[arrete.id])

    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 405  # Method Not Allowed


def test_delete_nonexistent_arrete(correct_perimetre_client_with_user_logged):
    url = reverse("gsl_notification:delete-arrete", args=[99999])
    response = correct_perimetre_client_with_user_logged.post(url)
    assert response.status_code == 404
