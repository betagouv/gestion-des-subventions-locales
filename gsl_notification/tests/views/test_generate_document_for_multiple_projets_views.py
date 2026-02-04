import io
import zipfile
from datetime import UTC, datetime
from html import unescape
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.tests.factories import (
    LettreNotificationFactory,
    ModeleLettreNotificationFactory,
)
from gsl_notification.utils import generate_pdf_for_generated_document
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL, LETTRE

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
def programmation_projets(perimetre):
    return ProgrammationProjetFactory.create_batch(
        3,
        dotation_projet__projet__dossier_ds__perimetre=perimetre,
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )


@pytest.fixture
def detr_lettre_modele(perimetre):
    return ModeleLettreNotificationFactory(dotation=DOTATION_DETR, perimetre=perimetre)


@pytest.fixture
def client(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


def test_choose_type_for_multiple_document_generation_with_wrong_dotation(client):
    url = reverse("notification:choose-generated-document-type-multiple", args=["raté"])
    response = client.get(url)
    assert response.status_code == 404


def test_choose_type_for_multiple_document_generation_no_id(client):
    # Must be selected (good perimetre, status and notified_at)
    ProgrammationProjetFactory.create_batch(
        3,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    # Must not be selected
    ProgrammationProjetFactory.create_batch(
        5,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    ProgrammationProjetFactory.create_batch(
        4,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=datetime.now(UTC),
    )

    url = reverse(
        "notification:choose-generated-document-type-multiple", args=[DOTATION_DETR]
    )
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["page_title"] == "3 projets DETR sélectionnés"
    assert (
        response.templates[0].name
        == "gsl_notification/generated_document/multiple/choose_generated_document_type.html"
    )


def test_choose_type_for_multiple_document_generation_no_id_and_with_filter_args(
    client,
):
    data = {"cout_min": "100000"}
    # Only two must be selected (100k and 150k)
    for amount in [50_000, 100_000, 150_000]:
        ProgrammationProjetFactory(
            dotation_projet__projet__dossier_ds__finance_cout_total=amount,
            dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            notified_at=None,
        )

    url = reverse(
        "notification:choose-generated-document-type-multiple", args=[DOTATION_DETR]
    )
    response = client.get(url, data)
    assert response.status_code == 200
    assert response.context["page_title"] == "2 projets DETR sélectionnés"
    assert (
        response.templates[0].name
        == "gsl_notification/generated_document/multiple/choose_generated_document_type.html"
    )


def test_choose_type_for_multiple_document_generation_one_id(
    client, programmation_projet
):
    url = (
        reverse(
            "notification:choose-generated-document-type-multiple",
            args=[programmation_projet.dotation_projet.dotation],
        )
        + f"?ids={programmation_projet.id}"
    )
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_notification:choose-generated-document-type",
        kwargs={"projet_id": programmation_projet.projet.id},
    )


def test_choose_type_with_one_wrong_perimetre_pp(client, programmation_projets):
    wrong_perimetre_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR
    )
    programmation_projets.append(wrong_perimetre_pp)
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:choose-generated-document-type-multiple", args=[DOTATION_DETR]
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 403
    # Check that the custom user message appears in the rendered 403 page
    assert (
        "Un ou plusieurs projets sont hors de votre périmètre."
        in response.content.decode("utf-8")
    )


@override_settings(DEBUG=False)
def test_choose_type_with_one_wrong_dotation_pp(client, programmation_projets):
    wrong_perimetre_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DSIL
    )
    programmation_projets.append(wrong_perimetre_pp)
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:choose-generated-document-type-multiple", args=[DOTATION_DETR]
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_choose_type_correctly(client, programmation_projets):
    pp_ids = [str(pp.id) for pp in programmation_projets]
    ids = ",".join(pp_ids)
    url = (
        reverse(
            "notification:choose-generated-document-type-multiple", args=[DOTATION_DETR]
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/generated_document/multiple/choose_generated_document_type.html"
    )
    assert response.context["page_title"] == "3 projets DETR sélectionnés"
    assert response.context["cancel_link"] == "/programmation/liste/DETR/"
    response = client.post(url, data={"document": "lettre"})
    assert response.status_code == 302
    assert (
        response["Location"]
        == reverse(
            "gsl_notification:select-modele-multiple",
            args=[DOTATION_DETR, "lettre"],
        )
        + f"?ids={'%2C'.join(pp_ids)}"
    )


## select_modele_multiple


def test_select_modele_multiple_method_allowed(
    client,
):
    url = reverse(
        "notification:select-modele-multiple",
        kwargs={"dotation": DOTATION_DETR, "document_type": LETTRE},
    )
    assert url == f"/notification/{DOTATION_DETR}/selection-d-un-modele/lettre"
    response = client.post(url)
    assert response.status_code == 405


@override_settings(DEBUG=False)
def test_select_modele_multiple_with_wrong_dotation(client):
    url = reverse("notification:select-modele-multiple", args=["raté", LETTRE])
    response = client.get(url)
    assert response.status_code == 404
    assert "Dotation inconnue" in unescape(response.content.decode("utf-8"))


@override_settings(DEBUG=False)
def test_select_modele_multiple_with_wrong_document_type(client):
    url = reverse("notification:select-modele-multiple", args=[DOTATION_DETR, "raté"])
    response = client.get(url)
    assert response.status_code == 404
    assert "Type de document inconnu" in unescape(response.content.decode("utf-8"))


def test_select_modele_multiple_no_id(client):
    # Must be selected (good perimetre, status and notified_at)
    ProgrammationProjetFactory.create_batch(
        3,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    # Must not be selected
    ProgrammationProjetFactory.create_batch(
        5,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    ProgrammationProjetFactory.create_batch(
        4,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=datetime.now(UTC),
    )

    url = reverse("notification:select-modele-multiple", args=[DOTATION_DETR, LETTRE])
    response = client.get(url)
    assert (
        response.templates[0].name
        == "gsl_notification/generated_document/multiple/select_modele.html"
    )
    assert response.context["page_super_title"] == "3 projets DETR sélectionnés"
    assert response.context["page_title"] == "Création de 3 lettres de notification"
    assert response.context["cancel_link"] == "/programmation/liste/DETR/"


def test_select_modele_multiple_no_id_and_with_filter_args(client):
    data = {"montant_retenu_max": "100000"}
    # Only two must be selected (50k and 100k)
    for amount in [50_000, 100_000, 150_000]:
        ProgrammationProjetFactory(
            montant=amount,
            dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            notified_at=None,
        )

    url = reverse("notification:select-modele-multiple", args=[DOTATION_DETR, LETTRE])
    response = client.get(url, data)
    assert (
        response.templates[0].name
        == "gsl_notification/generated_document/multiple/select_modele.html"
    )
    assert response.context["page_super_title"] == "2 projets DETR sélectionnés"
    assert response.context["page_title"] == "Création de 2 lettres de notification"
    assert response.context["cancel_link"] == "/programmation/liste/DETR/"


def test_select_modele_multiple_one_id(client, programmation_projet):
    url = (
        reverse(
            "notification:select-modele-multiple",
            args=[programmation_projet.dotation_projet.dotation, LETTRE],
        )
        + f"?ids={programmation_projet.id}"
    )
    response = client.get(url)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_notification:select-modele",
        kwargs={
            "dotation": programmation_projet.dotation_projet.dotation,
            "projet_id": programmation_projet.dotation_projet.projet.id,
            "document_type": LETTRE,
        },
    )


def test_select_modele_multiple_with_one_wrong_perimetre_pp(
    client, programmation_projets
):
    wrong_perimetre_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR
    )
    programmation_projets.append(wrong_perimetre_pp)
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse("notification:select-modele-multiple", args=[DOTATION_DETR, LETTRE])
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 403
    # Check that the custom user message appears in the response
    assert (
        "Un ou plusieurs projets sont hors de votre périmètre."
        in response.content.decode("utf-8")
    )


def test_select_modele_multiple_with_one_wrong_dotation_pp(
    client, programmation_projets
):
    wrong_perimetre_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DSIL
    )
    programmation_projets.append(wrong_perimetre_pp)
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse("notification:select-modele-multiple", args=[DOTATION_DETR, LETTRE])
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_select_modele_multiple_correctly(client, programmation_projets):
    modeles = ModeleLettreNotificationFactory.create_batch(
        2,
        dotation=DOTATION_DETR,
        perimetre=client.user.perimetre,
        name="Nom de modèle",
        description="Description de modèle",
    )
    pp_ids = [str(pp.id) for pp in programmation_projets]
    ids = ",".join(pp_ids)
    url = (
        reverse("notification:select-modele-multiple", args=[DOTATION_DETR, LETTRE])
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 200
    assert (
        response.templates[0].name
        == "gsl_notification/generated_document/multiple/select_modele.html"
    )
    assert len(response.context["modeles_list"]) == 2
    modele = response.context["modeles_list"][0]
    assert modele["name"] == "Nom de modèle"
    assert modele["description"] == "Description de modèle"
    assert len(modele["actions"]) == 1
    assert modele["actions"][0] == {
        "label": "S\xe9lectionner",
        "type": "submit",
        "href": f"/notification/{DOTATION_DETR}/sauvegarde/{LETTRE}/{modeles[0].id}?ids={'%2C'.join(pp_ids)}",
    }

    assert response.context["page_super_title"] == "3 projets DETR sélectionnés"
    assert response.context["page_title"] == "Création de 3 lettres de notification"
    assert response.context["cancel_link"] == "/programmation/liste/DETR/"


## save_documents


def test_save_documents_method_allowed(client, detr_lettre_modele):
    url = reverse(
        "notification:save-documents",
        kwargs={
            "dotation": DOTATION_DETR,
            "document_type": LETTRE,
            "modele_id": detr_lettre_modele.id,
        },
    )
    assert (
        url
        == f"/notification/{DOTATION_DETR}/sauvegarde/lettre/{detr_lettre_modele.id}"
    )
    response = client.get(url)
    assert response.status_code == 405


@override_settings(DEBUG=False)
def test_save_documents_with_wrong_dotation(client, detr_lettre_modele):
    url = reverse(
        "notification:save-documents", args=["raté", LETTRE, detr_lettre_modele.id]
    )
    response = client.post(url)
    assert response.status_code == 404
    assert "Dotation inconnue" in unescape(response.content.decode("utf-8"))


@override_settings(DEBUG=False)
def test_save_documents_with_wrong_document_type(client, detr_lettre_modele):
    url = reverse(
        "notification:save-documents",
        args=[DOTATION_DETR, "raté", detr_lettre_modele.id],
    )
    response = client.post(url)
    assert response.status_code == 404
    assert "Type de document inconnu" in unescape(response.content.decode("utf-8"))


def test_save_documents_no_id(client, detr_lettre_modele):
    # Must be selected (good perimetre, status and notified_at)
    pps = ProgrammationProjetFactory.create_batch(
        3,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    # Must not be selected
    ProgrammationProjetFactory.create_batch(
        5,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    ProgrammationProjetFactory.create_batch(
        4,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=datetime.now(UTC),
    )

    url = reverse(
        "notification:save-documents",
        args=[DOTATION_DETR, LETTRE, detr_lettre_modele.id],
    )
    response = client.post(url)

    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_programmation:programmation-projet-list-dotation", args=[DOTATION_DETR]
    )

    for pp in pps:
        assert hasattr(pp, "lettre_notification")
        assert pp.lettre_notification.modele == detr_lettre_modele
        assert pp.lettre_notification.created_by == client.user

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 25
    assert (
        "Les 3 lettres de notification ont bien été créées. <a href=/notification/DETR/telechargement/lettre"
        in message.message
    )
    assert (
        "title='Déclenche le téléchargement du fichier zip'>Télécharger le fichier zip</a>"
        in message.message
    )


def test_save_documents_no_id_and_with_filter_args(client, detr_lettre_modele):
    data = {"montant_retenu_max": "100000"}
    pps = []
    # Only two must be selected (50k and 100k)
    for amount in [50_000, 100_000, 150_000]:
        pps.append(
            ProgrammationProjetFactory(
                montant=amount,
                dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
                status=ProgrammationProjet.STATUS_ACCEPTED,
                notified_at=None,
            )
        )

    url = reverse(
        "notification:save-documents",
        args=[DOTATION_DETR, LETTRE, detr_lettre_modele.id],
    )
    response = client.post(url, data)

    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_programmation:programmation-projet-list-dotation", args=[DOTATION_DETR]
    )

    for pp in pps:
        pp.refresh_from_db()
        if pp.montant <= 100_000:
            assert hasattr(pp, "lettre_notification")
            assert pp.lettre_notification.modele == detr_lettre_modele
            assert pp.lettre_notification.created_by == client.user
        else:
            assert not hasattr(pp, "lettre_notification")

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 25
    assert (
        "Les 2 lettres de notification ont bien été créées. <a href=/notification/DETR/telechargement/lettre"
        in message.message
    )
    assert (
        "title='Déclenche le téléchargement du fichier zip'>Télécharger le fichier zip</a>"
        in message.message
    )


def test_save_documents_one_id(client, detr_lettre_modele, programmation_projet):
    url = (
        reverse(
            "notification:save-documents",
            args=[
                programmation_projet.dotation_projet.dotation,
                LETTRE,
                detr_lettre_modele.id,
            ],
        )
        + f"?ids={programmation_projet.id}"
    )
    response = client.post(url)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_notification:modifier-document",
        kwargs={
            "dotation": programmation_projet.dotation_projet.dotation,
            "projet_id": programmation_projet.dotation_projet.projet.id,
            "document_type": LETTRE,
        },
    )


def test_save_documents_with_modele_not_in_perimetre(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    modele = ModeleLettreNotificationFactory(dotation=DOTATION_DETR)
    url = (
        reverse(
            "notification:save-documents",
            args=[DOTATION_DETR, LETTRE, modele.id],
        )
        + f"?ids={ids}"
    )
    response = client.post(url)
    assert response.status_code == 404


def test_save_documents_with_modele_with_wrong_dotation(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    modele = ModeleLettreNotificationFactory(
        dotation=DOTATION_DSIL, perimetre=client.user.perimetre
    )
    url = (
        reverse(
            "notification:save-documents",
            args=[DOTATION_DETR, LETTRE, modele.id],
        )
        + f"?ids={ids}"
    )
    response = client.post(url)
    assert response.status_code == 404


def test_save_documents_with_not_existing_modele_id(client, programmation_projets):
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:save-documents",
            args=[DOTATION_DETR, LETTRE, 9999],
        )
        + f"?ids={ids}"
    )
    response = client.post(url)
    assert response.status_code == 404


def test_save_documents_with_one_wrong_perimetre_pp(
    client, programmation_projets, detr_lettre_modele
):
    wrong_perimetre_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR
    )
    programmation_projets.append(wrong_perimetre_pp)
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:save-documents",
            args=[DOTATION_DETR, LETTRE, detr_lettre_modele.id],
        )
        + f"?ids={ids}"
    )
    response = client.post(url)
    assert response.status_code == 403
    # Check that the custom user message appears in the response
    assert (
        "Un ou plusieurs projets sont hors de votre périmètre."
        in response.content.decode("utf-8")
    )


def test_save_documents_with_one_wrong_dotation_pp(
    client, programmation_projets, detr_lettre_modele
):
    wrong_dotation_pp = ProgrammationProjetFactory(
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        dotation_projet__dotation=DOTATION_DSIL,
    )
    programmation_projets.append(wrong_dotation_pp)
    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:save-documents",
            args=[DOTATION_DETR, LETTRE, detr_lettre_modele.id],
        )
        + f"?ids={ids}"
    )
    response = client.post(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_save_documents_correctly(client, programmation_projets, detr_lettre_modele):
    pp_ids = [str(pp.id) for pp in programmation_projets]
    ids = ",".join(pp_ids)
    url = (
        reverse(
            "notification:save-documents",
            args=[DOTATION_DETR, LETTRE, detr_lettre_modele.id],
        )
        + f"?ids={ids}"
    )
    response = client.post(url)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_programmation:programmation-projet-list-dotation", args=[DOTATION_DETR]
    )
    for pp in programmation_projets:
        assert hasattr(pp, "lettre_notification")
        assert pp.lettre_notification.modele == detr_lettre_modele
        assert pp.lettre_notification.created_by == client.user
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 25
    assert (
        "Les 3 lettres de notification ont bien été créées. <a href=/notification/DETR/telechargement/lettre?ids="
        in message.message
    )
    assert (
        "title='Déclenche le téléchargement du fichier zip'>Télécharger le fichier zip</a>"
        in message.message
    )


def test_save_documents_with_pp_which_already_have_a_lettre(
    client, programmation_projets, detr_lettre_modele
):
    pp = programmation_projets[0]
    lettre = LettreNotificationFactory(programmation_projet=pp)

    pp_ids = [str(pp.id) for pp in programmation_projets]
    ids = ",".join(pp_ids)
    url = (
        reverse(
            "notification:save-documents",
            args=[DOTATION_DETR, LETTRE, detr_lettre_modele.id],
        )
        + f"?ids={ids}"
    )
    response = client.post(url)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_programmation:programmation-projet-list-dotation", args=[DOTATION_DETR]
    )
    pp.refresh_from_db()
    assert pp.lettre_notification != lettre


## download_documents


def test_download_documents_method_allowed(client):
    url = reverse(
        "notification:download-documents",
        kwargs={
            "dotation": DOTATION_DETR,
            "document_type": LETTRE,
        },
    )
    assert url == f"/notification/{DOTATION_DETR}/telechargement/lettre"
    response = client.post(url)
    assert response.status_code == 405


@override_settings(DEBUG=False)
def test_download_documents_with_wrong_dotation(client):
    url = reverse("notification:download-documents", args=["raté", LETTRE])
    response = client.get(url)
    assert response.status_code == 404
    assert "Dotation inconnue" in unescape(response.content.decode("utf-8"))


@override_settings(DEBUG=False)
def test_download_documents_with_wrong_document_type(client):
    url = reverse(
        "notification:download-documents",
        args=[DOTATION_DETR, "raté"],
    )
    response = client.get(url)
    assert response.status_code == 404
    assert "Type de document inconnu" in unescape(response.content.decode("utf-8"))


def test_download_documents_no_id(client):
    pps = []
    # Must be selected (good perimetre, status and notified_at)
    pps += ProgrammationProjetFactory.create_batch(
        3,
        dotation_projet__dotation=DOTATION_DETR,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    # Must not be selected
    pps += ProgrammationProjetFactory.create_batch(
        5,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    pps += ProgrammationProjetFactory.create_batch(
        4,
        dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=datetime.now(UTC),
    )

    for pp in pps:
        LettreNotificationFactory(programmation_projet=pp)

    url = reverse(
        "notification:download-documents",
        args=[DOTATION_DETR, LETTRE],
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="documents.zip"'

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 3


def test_download_documents_no_id_with_filters(client):
    data = {"montant_demande_min": "100000"}

    pps = []
    for amount in [50_000, 100_000, 150_000]:
        pps.append(
            ProgrammationProjetFactory(
                dotation_projet__dotation=DOTATION_DETR,
                dotation_projet__projet__dossier_ds__perimetre=client.user.perimetre,
                dotation_projet__projet__dossier_ds__demande_montant=amount,
                status=ProgrammationProjet.STATUS_ACCEPTED,
                notified_at=None,
            )
        )

    for pp in pps:
        LettreNotificationFactory(programmation_projet=pp)

    url = reverse(
        "notification:download-documents",
        args=[DOTATION_DETR, LETTRE],
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        response = client.get(url, data)

    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="documents.zip"'

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 2


def test_download_documents_with_one_wrong_perimetre_pp(client, programmation_projets):
    wrong_perimetre_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR
    )
    programmation_projets.append(wrong_perimetre_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 403
    # Check that the custom user message appears in the response
    assert (
        "Un ou plusieurs projets sont hors de votre périmètre."
        in response.content.decode("utf-8")
    )


def test_download_documents_with_one_wrong_dotation_pp(client, programmation_projets):
    wrong_dotation_pp = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DSIL
    )
    programmation_projets.append(wrong_dotation_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_one_already_notified(client, programmation_projets):
    already_notified_pp = ProgrammationProjetFactory(notified_at=datetime.now(UTC))
    programmation_projets.append(already_notified_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_one_refused(client, programmation_projets):
    refuse_pp = ProgrammationProjetFactory(status=ProgrammationProjet.STATUS_REFUSED)
    programmation_projets.append(refuse_pp)

    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_missing_doc(client, programmation_projets):
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)
    pp_without_lettre = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DSIL
    )
    programmation_projets.append(pp_without_lettre)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_with_duplicate_id(client, programmation_projets):
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)

    ids = ",".join([str(pp.id) for pp in programmation_projets])
    ids += f",{str(programmation_projets[0].id)}"
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    response = client.get(url)
    assert response.status_code == 404
    assert (
        "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."
        in unescape(response.content.decode("utf-8"))
    )


def test_download_documents_correctly(client, programmation_projets):
    for pp in programmation_projets:
        LettreNotificationFactory(programmation_projet=pp)
    pp_ids = [str(pp.id) for pp in programmation_projets]
    ids = ",".join(pp_ids)
    url = (
        reverse(
            "notification:download-documents",
            args=[DOTATION_DETR, LETTRE],
        )
        + f"?ids={ids}"
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="documents.zip"'

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 3


def test_generate_pdf_for_document_unit(detr_lettre_modele, programmation_projet):
    document = LettreNotificationFactory(
        programmation_projet=programmation_projet,
        modele=detr_lettre_modele,
        content="<p>Test PDF</p>",
    )
    with patch(
        "gsl_notification.utils.get_logo_base64",
        return_value="mocked_base64",
    ):
        pdf_bytes = generate_pdf_for_generated_document(document)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 100
