import pytest
from django.urls import reverse

from gsl_notification.models import ModeleDocument
from gsl_notification.tests.factories import (
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)


def test_documents_url():
    url = reverse(
        "gsl_notification:documents",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/documents/"


# Arrete URLs


def test_select_modele_url():
    url = reverse(
        "gsl_notification:select-modele",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/selection-d-un-modele/"


def test_modifier_arrete_url():
    url = reverse(
        "gsl_notification:modifier-arrete",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/modifier-arrete/"


def test_arrete_download_url():
    url = reverse(
        "gsl_notification:arrete-download",
        kwargs={"arrete_id": 456},
    )
    assert url == "/notification/arrete/456/download/"


def test_arrete_delete_url():
    url = reverse(
        "gsl_notification:delete-arrete",
        kwargs={"arrete_id": 789},
    )
    assert url == "/notification/arrete/789/delete/"


# Arrete signés URLs


def test_create_arrete_signe_url():
    url = reverse(
        "gsl_notification:create-arrete-signe",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/creer-arrete-signe/"


def test_arrete_signe_download_url():
    url = reverse(
        "gsl_notification:arrete-signe-download",
        kwargs={"arrete_signe_id": 789},
    )
    assert url == "/notification/arrete-signe/789/download/"


def test_arrete_signe_delete_url():
    url = reverse(
        "gsl_notification:delete-arrete-signe",
        kwargs={"arrete_signe_id": 789},
    )
    assert url == "/notification/arrete-signe/789/delete/"


# Modele Arrete URLs
def test_modele_arrete_liste_url():
    url = reverse(
        "gsl_notification:modele-liste",
        kwargs={"dotation": "DSIL"},
    )
    assert url == "/notification/modeles/liste/DSIL/"


def test_create_modele_arrete_wizard_url():
    url = reverse(
        "gsl_notification:modele-creer",
        kwargs={"dotation": "DETR", "modele_type": "arrete"},
    )
    assert url == "/notification/modeles/nouveau/arrete/DETR/"


@pytest.mark.parametrize(
    ("modele_type, factory"),
    (
        (ModeleDocument.TYPE_ARRETE, ModeleArreteFactory),
        (ModeleDocument.TYPE_LETTRE, ModeleLettreNotificationFactory),
    ),
)
@pytest.mark.django_db
def test_update_modele_url(modele_type, factory):
    modele = factory()
    url = reverse(
        "gsl_notification:modele-modifier",
        kwargs={"modele_type": modele_type, "modele_id": modele.id},
    )
    assert url == f"/notification/modeles/modifier/{modele_type}/{modele.id}/"


@pytest.mark.parametrize(
    ("modele_type, factory"),
    (
        (ModeleDocument.TYPE_ARRETE, ModeleArreteFactory),
        (ModeleDocument.TYPE_LETTRE, ModeleLettreNotificationFactory),
    ),
)
@pytest.mark.django_db
def test_duplicate_modele_url(modele_type, factory):
    modele = factory()
    url = reverse(
        "gsl_notification:modele-dupliquer",
        kwargs={"modele_type": modele_type, "modele_id": modele.id},
    )
    assert url == f"/notification/modeles/dupliquer/{modele_type}/{modele.id}/"


@pytest.mark.django_db
def test_delete_modele_url():
    modele = ModeleArreteFactory()
    url = reverse(
        "gsl_notification:delete-modele-arrete", kwargs={"modele_arrete_id": modele.id}
    )
    assert url == f"/notification/modeles/{modele.id}/"


def test_get_generic_modele_url():
    url = reverse(
        "gsl_notification:get-generic-modele-template", kwargs={"dotation": "DETR"}
    )
    assert url == "/notification/modeles/generique/DETR/"
