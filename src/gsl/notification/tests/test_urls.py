import pytest
from django.urls import NoReverseMatch, reverse

from dn.sync.models import Dotation
from gsl.notification.models import GeneratedDocument


def test_documents_url():
    url = reverse(
        "gsl_notification:documents",
        kwargs={"projet_id": 123},
    )
    assert url == "/notification/123/documents/"


# Document URLs


@pytest.mark.parametrize(
    "document_type", (GeneratedDocument.Type.ARRETE, GeneratedDocument.Type.LETTRE)
)
def test_select_modele_url(document_type):
    url = reverse(
        "gsl_notification:select-modele",
        kwargs={
            "projet_id": 123,
            "dotation": Dotation.DETR,
            "document_type": document_type,
        },
    )
    assert (
        url
        == f"/notification/123/selection-d-un-modele/{Dotation.DETR}/{document_type}"
    )


@pytest.mark.parametrize(
    "document_type", (GeneratedDocument.Type.ARRETE, GeneratedDocument.Type.LETTRE)
)
def test_modifier_document_url(document_type):
    url = reverse(
        "gsl_notification:modifier-document",
        kwargs={
            "projet_id": 123,
            "dotation": Dotation.DETR,
            "document_type": document_type,
        },
    )
    assert url == f"/notification/123/modifier-document/{Dotation.DETR}/{document_type}"


def test_document_download_url():
    url = reverse("gsl_notification:document-download", kwargs={"document_id": 456})
    assert url == "/notification/document/456/download/"


def test_document_view_url():
    url = reverse("gsl_notification:document-view", kwargs={"document_id": 456})
    assert url == "/notification/document/456/view/"


def test_document_delete_url():
    url = reverse("gsl_notification:delete-document", kwargs={"document_id": 789})
    assert url == "/notification/document/789/delete/"


# Uploaded documents URLs


@pytest.mark.parametrize(
    "fragment_name, expected",
    (
        (
            "upload_document_analyze",
            "/fragment/gsl_notification/upload_document_analyze/123/",
        ),
        (
            "manual_document_attach",
            "/fragment/gsl_notification/manual_document_attach/123/",
        ),
    ),
)
def test_upload_document_step_urls(fragment_name, expected):
    assert (
        reverse(f"fragment:gsl_notification:{fragment_name}", kwargs={"pk": 123})
        == expected
    )


def test_uploaded_document_download_url():
    url = reverse(
        "gsl_notification:uploaded-document-download", kwargs={"document_id": 789}
    )
    assert url == "/notification/document-televerse/789/download/"


def test_uploaded_document_delete_url():
    url = reverse(
        "gsl_notification:delete-uploaded-document", kwargs={"document_id": 789}
    )
    assert url == "/notification/document-televerse/789/delete/"


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


def test_update_modele_url():
    url = reverse("gsl_notification:modele-modifier", kwargs={"modele_id": 12})
    assert url == "/notification/modeles/modifier/12/"


def test_duplicate_modele_url():
    url = reverse("gsl_notification:modele-dupliquer", kwargs={"modele_id": 12})
    assert url == "/notification/modeles/dupliquer/12/"


def test_delete_modele_url():
    url = reverse("gsl_notification:delete-modele", kwargs={"modele_id": 12})
    assert url == "/notification/modeles/12/"


def test_unknown_generated_document_type_does_not_resolve():
    with pytest.raises(NoReverseMatch):
        reverse(
            "gsl_notification:modele-creer",
            kwargs={"dotation": "DETR", "modele_type": "inconnu"},
        )


@pytest.mark.parametrize("dotation", (Dotation.DETR, Dotation.DSIL))
def test_get_generic_modele_url(dotation):
    url = reverse(
        "gsl_notification:get-generic-modele-template", kwargs={"dotation": dotation}
    )
    assert url == f"/notification/modeles/generique/{dotation}/"
