import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
    PerimetreFactory,
)
from gsl_notification.models import ModeleArrete
from gsl_notification.tests.factories import (
    ArreteFactory,
    ArreteSigneFactory,
    ModeleArreteFactory,
)
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
def client(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


pytestmark = pytest.mark.django_db


### modele-arrete-create


def test_create_arrete_views(client):
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
    response = client.post(url, data_step_1)

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
    response = client.post(url, data_step_2)
    assert response.status_code == 200
    assert not response.context["form"].errors, (
        f"Errors in step 2 - {response.context['form'].errors}"
    )
    assert (
        response.context["form"]["content"].value()
        == "<p>Écrivez ici le contenu de votre arrêté</p>"
    )

    data_step_3 = {
        "2-content": "<p>Le contenu HTML du modèle d’arrêté</p>",
        "create_model_arrete_wizard-current_step": 2,
    }
    response = client.post(url, data_step_3)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "notification:modele-arrete-liste",
        kwargs={"dotation": DOTATION_DETR},
    )

    modele_en_base = ModeleArrete.objects.first()
    assert modele_en_base
    assert modele_en_base.created_by == client.user
    assert modele_en_base.logo_alt_text == "Texte alternatif du logo"


# UPDATE


def test_update_modele_arrete_view_get_initial_data(client, perimetre):
    """Test that the update view displays initial data correctly"""
    modele_arrete = ModeleArreteFactory(
        name="The Name",
        description="The Description",
        logo_alt_text="The Alt Text",
        top_right_text="The Top Right",
        content="<p>The Content</p>",
        perimetre=perimetre,
        dotation=DOTATION_DETR,
    )
    url = reverse(
        "gsl_notification:modele-arrete-modifier",
        kwargs={"modele_arrete_id": modele_arrete.id},
    )

    # Test step 0 (title and description)
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["form"]["name"].value() == "The Name"
    assert response.context["form"]["description"].value() == "The Description"


def test_update_modele_arrete_view_complete_workflow(client, perimetre):
    """Test complete update workflow through all steps"""
    initial_logo = SimpleUploadedFile(
        "initial_logo.png", b"initial logo content", content_type="image/png"
    )
    initial_logo_name = initial_logo.name

    modele_arrete = ModeleArreteFactory(
        name="The Name",
        description="The Description",
        logo=initial_logo,
        logo_alt_text="The Alt Text",
        top_right_text="The Top Right",
        content="<p>The Content</p>",
        perimetre=perimetre,
        dotation=DOTATION_DETR,
    )
    url = reverse(
        "gsl_notification:modele-arrete-modifier",
        kwargs={"modele_arrete_id": modele_arrete.id},
    )

    # Step 1: Update name and description
    data_step_1 = {
        "0-name": "Updated Name",
        "0-description": "Updated Description",
        "update_modele_arrete-current_step": 0,
    }
    response = client.post(url, data_step_1)
    assert response.status_code == 200
    assert not response.context["form"].errors
    assert response.context["form"]["logo_alt_text"].value() == "The Alt Text"
    assert response.context["form"]["top_right_text"].value() == "The Top Right"

    # Step 2: Update logo and header info
    data_step_2 = {
        "1-logo": SimpleUploadedFile(
            "new_test.png", b"new content", content_type="image/png"
        ),
        "1-logo_alt_text": "Updated Alt Text",
        "1-top_right_text": "Updated Top Right<br>Text",
        "update_modele_arrete-current_step": 1,
    }
    response = client.post(url, data_step_2)
    assert response.status_code == 200
    assert not response.context["form"].errors
    assert response.context["form"]["content"].value() == "<p>The Content</p>"

    # Step 3: Update content and complete
    data_step_3 = {
        "2-content": "<p>Updated HTML content</p>",
        "update_modele_arrete-current_step": 2,
    }
    response = client.post(url, data_step_3)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_notification:modele-arrete-liste",
        kwargs={"dotation": DOTATION_DETR},
    )

    # Verify the model was updated
    modele_arrete.refresh_from_db()
    assert modele_arrete.name == "Updated Name"
    assert modele_arrete.description == "Updated Description"
    assert modele_arrete.logo_alt_text == "Updated Alt Text"
    assert modele_arrete.top_right_text == "Updated Top Right<br>Text"
    assert modele_arrete.content == "<p>Updated HTML content</p>"
    assert modele_arrete.logo.name != initial_logo_name
    assert modele_arrete.logo.name.startswith("new_test")


def test_update_modele_arrete_view_wrong_perimetre(client):
    """Test that users cannot update models from different perimeters"""
    different_perimetre = PerimetreDepartementalFactory()
    modele_arrete = ModeleArreteFactory(
        perimetre=different_perimetre, dotation=DOTATION_DETR
    )
    url = reverse(
        "gsl_notification:modele-arrete-modifier",
        kwargs={"modele_arrete_id": modele_arrete.id},
    )

    response = client.get(url)
    assert response.status_code == 404


def test_update_nonexistent_modele_arrete(client):
    """Test updating a non-existent model returns 404"""
    url = reverse(
        "gsl_notification:modele-arrete-modifier",
        kwargs={"modele_arrete_id": 99999},
    )

    response = client.get(url)
    assert response.status_code == 404


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


def test_delete_nonexistent_modele_arrete(client):
    url = reverse("gsl_notification:delete-modele-arrete", args=[99999])
    response = client.post(url)
    assert response.status_code == 404
