import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_notification.models import ModeleArrete
from gsl_notification.tests.factories import (
    ArreteFactory,
    ModeleArreteFactory,
)
from gsl_projet.constants import DOTATION_DETR

### modele-arrete-create


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
    assert response["Location"] == reverse(
        "notification:modele-arrete-liste",
        kwargs={"dotation": DOTATION_DETR},
    )

    modele_en_base = ModeleArrete.objects.first()
    assert modele_en_base
    assert modele_en_base.created_by == correct_perimetre_client_with_user_logged.user
    assert modele_en_base.logo_alt_text == "Texte alternatif du logo"


### delete-modele-arrete


def test_delete_modele_arrete_with_correct_perimetre():
    departement_perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=departement_perimetre)
    client = ClientWithLoggedUserFactory(user)
    modele_arrete = ModeleArreteFactory(
        perimetre=departement_perimetre, name="Mon modèle"
    )
    url = reverse("gsl_notification:delete-modele-arrete", args=[modele_arrete.id])

    response = client.post(url)

    expected_redirect_url = reverse(
        "gsl_notification:modele-arrete-liste", args=[modele_arrete.dotation]
    )
    assert response.status_code == 302
    assert response.url == expected_redirect_url

    assert ModeleArrete.objects.count() == 0
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 20
    assert message.message == "Le modèle d’arrêté “Mon modèle” a été supprimé."


def test_delete_modele_arrete_with_modele_used_by_an_arrete():
    departement_perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=departement_perimetre)
    client = ClientWithLoggedUserFactory(user)
    modele_arrete = ModeleArreteFactory(perimetre=departement_perimetre)
    ArreteFactory(modele=modele_arrete)
    url = reverse("gsl_notification:delete-modele-arrete", args=[modele_arrete.id])

    response = client.post(url)

    expected_redirect_url = reverse(
        "gsl_notification:modele-arrete-liste", args=[modele_arrete.dotation]
    )
    assert response.status_code == 302
    assert response.url == expected_redirect_url

    assert ModeleArrete.objects.count() == 1, (
        "On s'attend à ce que le ModeleArrete ne soit pas supprimé"
    )
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert (
        message.message
        == "Le modèle n'a pas été supprimé car il est utilisé par 1 arrêté(s)."
    )
    assert message.extra_tags == "alert"


def test_delete_modele_arrete_with_wrong_perimetre():
    user = CollegueFactory(perimetre=PerimetreDepartementalFactory())
    client = ClientWithLoggedUserFactory(user)
    modele_arrete = ModeleArreteFactory(perimetre=PerimetreDepartementalFactory())
    url = reverse("gsl_notification:delete-modele-arrete", args=[modele_arrete.id])

    response = client.post(url)

    assert response.status_code == 404

    assert ModeleArrete.objects.count() == 1


def test_delete_nonexistent_modele_arrete(correct_perimetre_client_with_user_logged):
    url = reverse("gsl_notification:delete-modele-arrete", args=[99999])
    response = correct_perimetre_client_with_user_logged.post(url)
    assert response.status_code == 404
