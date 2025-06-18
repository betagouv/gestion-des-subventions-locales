import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.tests.factories import ArreteSigneFactory
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


### create-arrete


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


### get-arrete


def test_get_arrete_url_with_correct_perimetre_and_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:get-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/arrete-signe/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 302
    assert (
        response["Location"] == f"/notification/{programmation_projet.id}/creer-arrete/"
    )


def test_get_arrete_url_with_correct_perimetre_and_with_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    ArreteSigneFactory(programmation_projet=programmation_projet)
    url = reverse(
        "notification:get-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/arrete-signe/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "with_arrete",
    [
        True,
        False,
    ],
)
def test_get_arrete_url_without_correct_perimetre_and_without_arrete(
    programmation_projet, different_perimetre_client_with_user_logged, with_arrete
):
    if with_arrete:
        ArreteSigneFactory(programmation_projet=programmation_projet)

    url = reverse(
        "notification:get-arrete",
        kwargs={"programmation_projet_id": programmation_projet.id},
    )
    assert url == f"/notification/{programmation_projet.id}/arrete-signe/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


### arrete-signe-download


def test_arrete_signe_download_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged,
):
    url = reverse(
        "notification:arrete-signe-download",
        kwargs={"arrete_signe_id": 1000},
    )
    assert url == "/notification/arrete/1000/download/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_arrete_signe_download_url_with_correct_perimetre_and_with_arrete(
    arrete_signe, correct_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:arrete-signe-download",
        kwargs={"arrete_signe_id": arrete_signe.id},
    )
    assert url == f"/notification/arrete/{arrete_signe.id}/download/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200


def test_arrete_signe_download_url_without_correct_perimetre_and_without_arrete(
    arrete_signe, different_perimetre_client_with_user_logged
):
    url = reverse(
        "notification:arrete-signe-download",
        kwargs={"arrete_signe_id": arrete_signe.id},
    )
    assert url == f"/notification/arrete/{arrete_signe.id}/download/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404
