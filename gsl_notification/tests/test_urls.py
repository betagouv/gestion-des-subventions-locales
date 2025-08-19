import pytest
from django.urls import reverse

from gsl_notification.tests.factories import (
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_projet.constants import (
    ANNEXE,
    ARRETE,
    ARRETE_ET_LETTRE_SIGNES,
    DOTATION_DETR,
    DOTATION_DSIL,
    LETTRE,
)


def test_documents_url():
    url = reverse(
        "gsl_notification:documents",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/documents/"


# Document URLs


def test_choose_type_for_document_generation_url():
    url = reverse(
        "gsl_notification:choose-generated-document-type",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/choix-du-type/"


@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_select_modele_url(document_type):
    url = reverse(
        "gsl_notification:select-modele",
        kwargs={"programmation_projet_id": 123, "document_type": document_type},
    )
    assert url == f"/notification/123/selection-d-un-modele/{document_type}"


@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_modifier_document_url(document_type):
    url = reverse(
        "gsl_notification:modifier-document",
        kwargs={"programmation_projet_id": 123, "document_type": document_type},
    )
    assert url == f"/notification/123/modifier-document/{document_type}"


@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_document_download_url(document_type):
    url = reverse(
        "gsl_notification:document-download",
        kwargs={"document_type": document_type, "document_id": 456},
    )
    assert url == f"/notification/document/{document_type}/456/download/"


@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_document_view_url(document_type):
    url = reverse(
        "gsl_notification:document-view",
        kwargs={"document_type": document_type, "document_id": 456},
    )
    assert url == f"/notification/document/{document_type}/456/view/"


@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_document_delete_url(document_type):
    url = reverse(
        "gsl_notification:delete-document",
        kwargs={"document_type": document_type, "document_id": 789},
    )
    assert url == f"/notification/document/{document_type}/789/delete/"


# Multiple document URLs


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
def test_choose_type_for_multiple_document_generation(dotation):
    url = reverse(
        "gsl_notification:choose-generated-document-type-multiple",
        kwargs={"dotation": dotation},
    )
    assert url == f"/notification/{dotation}/choix-du-type/"


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_select_modele_multiple(dotation, document_type):
    url = reverse(
        "gsl_notification:select-modele-multiple",
        kwargs={"dotation": dotation, "document_type": document_type},
    )
    assert url == f"/notification/{dotation}/selection-d-un-modele/{document_type}"


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_save_documents(dotation, document_type):
    url = reverse(
        "gsl_notification:save-documents",
        kwargs={"dotation": dotation, "document_type": document_type, "modele_id": 12},
    )
    assert url == f"/notification/{dotation}/sauvegarde/{document_type}/12"


# Uploaded documents URLs


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNES, ANNEXE))
def test_create_arrete_et_lettre_signes_url(doc_type):
    url = reverse(
        "gsl_notification:upload-a-document",
        kwargs={"programmation_projet_id": 123, "document_type": doc_type},
    )
    assert url == f"/notification/123/televersement/{doc_type}/creer/"


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNES, ANNEXE))
def test_uploaded_document_download_url(doc_type):
    url = reverse(
        "gsl_notification:uploaded-document-download",
        kwargs={"document_type": doc_type, "document_id": 789},
    )
    assert url == f"/notification/document-televerse/{doc_type}/789/download/"


@pytest.mark.parametrize("doc_type", (ARRETE_ET_LETTRE_SIGNES, ANNEXE))
def test_uploaded_document_delete_url(doc_type):
    url = reverse(
        "gsl_notification:delete-uploaded-document",
        kwargs={"document_type": doc_type, "document_id": 789},
    )
    assert url == f"/notification/document-televerse/{doc_type}/789/delete/"


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
        (ARRETE, ModeleArreteFactory),
        (LETTRE, ModeleLettreNotificationFactory),
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
        (ARRETE, ModeleArreteFactory),
        (LETTRE, ModeleLettreNotificationFactory),
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


@pytest.mark.parametrize(
    ("modele_type, factory"),
    (
        (ARRETE, ModeleArreteFactory),
        (LETTRE, ModeleLettreNotificationFactory),
    ),
)
@pytest.mark.django_db
def test_delete_modele_url(modele_type, factory):
    modele = factory()
    url = reverse(
        "gsl_notification:delete-modele",
        kwargs={"modele_type": modele_type, "modele_id": modele.id},
    )
    assert url == f"/notification/modeles/{modele_type}/{modele.id}/"


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
def test_get_generic_modele_url(dotation):
    url = reverse(
        "gsl_notification:get-generic-modele-template", kwargs={"dotation": dotation}
    )
    assert url == f"/notification/modeles/generique/{dotation}/"
