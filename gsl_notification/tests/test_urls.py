import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreFactory,
)
from gsl_notification.models import ModeleArrete
from gsl_notification.tests.factories import ArreteSigneFactory
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import DOTATION_DETR


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


def test_documents_url():
    url = reverse(
        "gsl_notification:documents",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/documents/"


def test_modifier_arrete_url():
    url = reverse(
        "gsl_notification:modifier-arrete",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/modifier-arrete/"


def test_create_arrete_signe_url():
    url = reverse(
        "gsl_notification:create-arrete-signe",
        kwargs={"programmation_projet_id": 123},
    )
    assert url == "/notification/123/creer-arrete-signe/"


def test_arrete_download_url():
    url = reverse(
        "gsl_notification:arrete-download",
        kwargs={"arrete_id": 456},
    )
    assert url == "/notification/arrete/456/download/"


def test_arrete_signe_download_url():
    url = reverse(
        "gsl_notification:arrete-signe-download",
        kwargs={"arrete_signe_id": 789},
    )
    assert url == "/notification/arrete-signe/789/download/"


# Modèles d'arrêté


@pytest.mark.django_db
def test_create_arrete_views(correct_perimetre_client_with_user_logged):
    assert not ModeleArrete.objects.exists()
    url = reverse(
        "notification:modele-arrete-creer",
        kwargs={"dotation": DOTATION_DETR},
    )
    data_step_1 = {
        "0-name": "Nom de l’arrêté",
        "0-description": "Description de l’arrêté",
        "create_model_arrete_wizard-current_step": 0,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data_step_1)

    assert response.status_code == 200
    assert not response.context["form"].errors, (
        f"Errors in step 1 - {response.context['form'].errors}"
    )

    data_step_2 = {
        "1-logo": SimpleUploadedFile("test.png", b"youpi", content_type="image/png"),
        "1-logo_alt_text": "Texte alternatif du logo",
        "1-top_right_text": "Il fait froid<br>Oui<br>Je n'ai pas honte de cette blague",
        "create_model_arrete_wizard-current_step": 1,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data_step_2)
    assert response.status_code == 200
    assert not response.context["form"].errors, (
        f"Errors in step 2 - {response.context['form'].errors}"
    )

    data_step_3 = {
        "2-content": "<p>Le contenu HTML du modèle d’arrêté</p>",
        "create_model_arrete_wizard-current_step": 2,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data_step_3)
    assert response.status_code == 302

    modele_en_base = ModeleArrete.objects.first()
    assert modele_en_base
    assert modele_en_base.created_by == correct_perimetre_client_with_user_logged.user
    assert modele_en_base.logo_alt_text == "Texte alternatif du logo"
