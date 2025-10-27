import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
    PerimetreFactory,
)
from gsl_notification.models import (
    ModeleArrete,
    ModeleLettreNotification,
)
from gsl_notification.tests.factories import (
    ArreteEtLettreSignesFactory,
    ArreteFactory,
    LettreNotificationFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import ARRETE, DOTATION_DETR, DOTATION_DSIL, LETTRE


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def programmation_projet(perimetre):
    return ProgrammationProjetFactory(dotation_projet__projet__perimetre=perimetre)


@pytest.fixture
def arrete_et_lettre_signes(programmation_projet):
    return ArreteEtLettreSignesFactory(programmation_projet=programmation_projet)


@pytest.fixture
def client(perimetre):
    user = CollegueFactory(perimetre=perimetre)
    return ClientWithLoggedUserFactory(user)


pytestmark = pytest.mark.django_db

# LIST


def test_list_modele_view(client, perimetre):
    # Must be in context
    ModeleArreteFactory.create_batch(2, perimetre=perimetre, dotation=DOTATION_DETR)
    ModeleLettreNotificationFactory.create_batch(
        3, perimetre=perimetre, dotation=DOTATION_DETR
    )

    # Must NOT be in context
    ModeleArreteFactory.create_batch(
        6, perimetre=PerimetreDepartementalFactory(), dotation=DOTATION_DETR
    )
    ModeleArreteFactory.create_batch(8, perimetre=perimetre, dotation=DOTATION_DSIL)
    ModeleLettreNotificationFactory.create_batch(
        7, perimetre=PerimetreDepartementalFactory(), dotation=DOTATION_DETR
    )
    ModeleLettreNotificationFactory.create_batch(
        9, perimetre=perimetre, dotation=DOTATION_DSIL
    )

    url = reverse(
        "notification:modele-liste",
        kwargs={"dotation": DOTATION_DETR},
    )
    response = client.get(url)
    assert len(response.context["object_list"]) == 5  # = 3 + 2


# CREATE


@pytest.mark.parametrize(
    ("modele_type, _class"),
    (
        (ARRETE, ModeleArrete),
        (LETTRE, ModeleLettreNotification),
    ),
)
def test_create_modele_arrete_views(client, modele_type, _class):
    assert not _class.objects.exists()
    url = reverse(
        "notification:modele-creer",
        kwargs={"modele_type": modele_type, "dotation": DOTATION_DETR},
    )
    data_step_1 = {
        "0-name": "Nom de l’arrêté",
        "0-description": "Description de l’arrêté",
        "create_model_document_wizard-current_step": 0,
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
        "create_model_document_wizard-current_step": 1,
    }
    response = client.post(url, data_step_2)
    assert response.status_code == 200
    assert not response.context["form"].errors, (
        f"Errors in step 2 - {response.context['form'].errors}"
    )
    assert (
        response.context["form"]["content"].value()
        == "<p>Écrivez ici le contenu de votre modèle</p>"
    )

    data_step_3 = {
        "2-content": "<p>Le contenu HTML du modèle</p>",
        "create_model_document_wizard-current_step": 2,
    }
    response = client.post(url, data_step_3)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "notification:modele-liste",
        kwargs={"dotation": DOTATION_DETR},
    )

    modele_en_base = _class.objects.first()
    assert modele_en_base
    assert modele_en_base.created_by == client.user
    assert modele_en_base.logo_alt_text == "Texte alternatif du logo"


# UPDATE


@pytest.mark.parametrize(
    ("modele_type, factory"),
    (
        (ARRETE, ModeleArreteFactory),
        (LETTRE, ModeleLettreNotificationFactory),
    ),
)
def test_update_modele_arrete_view_complete_workflow(
    client, perimetre, modele_type, factory
):
    initial_logo = SimpleUploadedFile(
        "initial_logo.png", b"initial logo content", content_type="image/png"
    )
    initial_logo_name = initial_logo.name

    modele_document = factory(
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
        "gsl_notification:modele-modifier",
        kwargs={"modele_type": modele_type, "modele_id": modele_document.id},
    )

    # Test step 0 (title and description)
    response = client.get(url)
    assert response.status_code == 200
    assert response.context["form"]["name"].value() == "The Name"
    assert response.context["form"]["description"].value() == "The Description"

    # Step 1: Update name and description
    data_step_1 = {
        "0-name": "Updated Name",
        "0-description": "Updated Description",
        "update_modele-current_step": 0,
    }
    response = client.post(url, data_step_1)
    assert response.status_code == 200
    assert not response.context["form"].errors
    assert response.context["form"]["logo_alt_text"].value() == "The Alt Text"
    assert response.context["form"]["top_right_text"].value() == "The Top Right"

    # Step 2: Update logo and header info
    data_step_2 = {
        "1-logo": SimpleUploadedFile(
            "new_logo.png", b"new content", content_type="image/png"
        ),
        "1-logo_alt_text": "Updated Alt Text",
        "1-top_right_text": "Updated Top Right<br>Text",
        "update_modele-current_step": 1,
    }
    response = client.post(url, data_step_2)
    assert response.status_code == 200
    assert not response.context["form"].errors
    assert response.context["form"]["content"].value() == "<p>The Content</p>"

    # Step 3: Update content and complete
    data_step_3 = {
        "2-content": "<p>Updated HTML content</p>",
        "update_modele-current_step": 2,
    }
    response = client.post(url, data_step_3)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_notification:modele-liste",
        kwargs={"dotation": DOTATION_DETR},
    )

    # Verify the model was updated
    modele_document.refresh_from_db()
    assert modele_document.name == "Updated Name"
    assert modele_document.description == "Updated Description"
    assert modele_document.logo_alt_text == "Updated Alt Text"
    assert modele_document.top_right_text == "Updated Top Right<br>Text"
    assert modele_document.content == "<p>Updated HTML content</p>"
    assert modele_document.logo.name != initial_logo_name
    assert "new_logo" in modele_document.logo.name


@pytest.mark.parametrize(
    ("modele_type, factory"),
    (
        (ARRETE, ModeleArreteFactory),
        (LETTRE, ModeleLettreNotificationFactory),
    ),
)
def test_update_modele_arrete_view_wrong_perimetre(client, modele_type, factory):
    """Test that users cannot update models from different perimeters"""
    different_perimetre = PerimetreDepartementalFactory()
    modele_document = factory(perimetre=different_perimetre, dotation=DOTATION_DETR)
    url = reverse(
        "gsl_notification:modele-modifier",
        kwargs={"modele_type": modele_type, "modele_id": modele_document.id},
    )

    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("modele_type"),
    (
        ARRETE,
        LETTRE,
    ),
)
def test_update_nonexistent_modele_arrete(client, modele_type):
    """Test updating a non-existent model returns 404"""
    url = reverse(
        "gsl_notification:modele-modifier",
        kwargs={"modele_type": modele_type, "modele_id": 99999},
    )

    response = client.get(url)
    assert response.status_code == 404


# DUPLICATE


@pytest.mark.parametrize(
    ("modele_type, _class, factory"),
    (
        (ARRETE, ModeleArrete, ModeleArreteFactory),
        (
            LETTRE,
            ModeleLettreNotification,
            ModeleLettreNotificationFactory,
        ),
    ),
)
def test_duplicate_modele_arrete_view_complete_workflow(
    client, perimetre, modele_type, _class, factory
):
    initial_logo = SimpleUploadedFile(
        "initial_logo.png", b"initial logo content", content_type="image/png"
    )
    initial_logo_name = initial_logo.name

    initial_modele = factory(
        name="The Name",
        description="The Description",
        logo=initial_logo,
        logo_alt_text="The Alt Text",
        top_right_text="The Top Right",
        content="<p>The Content</p>",
        perimetre=perimetre,
        dotation=DOTATION_DETR,
        created_by=CollegueFactory(perimetre=perimetre),
    )
    url = reverse(
        "gsl_notification:modele-dupliquer",
        kwargs={"modele_type": modele_type, "modele_id": initial_modele.id},
    )

    # Step 1: Update name and description
    data_step_1 = {
        "0-name": "Updated Name",
        "0-description": "Updated Description",
        "duplicate_modele-current_step": 0,
    }
    response = client.post(url, data_step_1)
    assert response.status_code == 200
    assert not response.context["form"].errors
    assert isinstance(response.context["form"]["logo"].value(), FieldFile)
    assert "initial_logo" in response.context["form"]["logo"].value().name
    assert response.context["form"]["logo_alt_text"].value() == "The Alt Text"
    assert response.context["form"]["top_right_text"].value() == "The Top Right"

    # Step 2: Update logo and header info
    data_step_2 = {
        "1-logo": SimpleUploadedFile(
            "new_logo.png", b"new content", content_type="image/png"
        ),
        "1-logo_alt_text": "Updated Alt Text",
        "1-top_right_text": "Updated Top Right<br>Text",
        "duplicate_modele-current_step": 1,
    }
    response = client.post(url, data_step_2)
    assert response.status_code == 200
    assert not response.context["form"].errors
    assert response.context["form"]["content"].value() == "<p>The Content</p>"

    # Step 3: Update content and complete
    data_step_3 = {
        "2-content": "<p>Updated HTML content</p>",
        "duplicate_modele-current_step": 2,
    }
    response = client.post(url, data_step_3)
    assert response.status_code == 302
    assert response["Location"] == reverse(
        "gsl_notification:modele-liste",
        kwargs={"dotation": DOTATION_DETR},
    )

    # Verify the model was updated
    new_modele = _class.objects.last()
    assert new_modele.name == "Updated Name"
    assert new_modele.description == "Updated Description"
    assert new_modele.logo_alt_text == "Updated Alt Text"
    assert new_modele.top_right_text == "Updated Top Right<br>Text"
    assert new_modele.content == "<p>Updated HTML content</p>"
    assert initial_logo_name not in new_modele.logo.name
    assert "new_logo" in new_modele.logo.name
    assert new_modele.dotation == DOTATION_DETR
    assert new_modele.perimetre == perimetre
    assert new_modele.created_by == client.user


@pytest.mark.parametrize(
    ("modele_type, factory"),
    (
        (ARRETE, ModeleArreteFactory),
        (LETTRE, ModeleLettreNotificationFactory),
    ),
)
def test_duplicate_modele_arrete_view_wrong_perimetre(client, modele_type, factory):
    """Test that users cannot update models from different perimeters"""
    different_perimetre = PerimetreDepartementalFactory()
    modele = factory(perimetre=different_perimetre, dotation=DOTATION_DETR)
    url = reverse(
        "gsl_notification:modele-dupliquer",
        kwargs={"modele_type": modele_type, "modele_id": modele.id},
    )

    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("modele_type"),
    (
        ARRETE,
        LETTRE,
    ),
)
def test_duplicate_nonexistent_modele_arrete(client, modele_type):
    """Test updating a non-existent model returns 404"""
    url = reverse(
        "gsl_notification:modele-dupliquer",
        kwargs={"modele_type": modele_type, "modele_id": 99999},
    )

    response = client.get(url)
    assert response.status_code == 404


# DELETE


@pytest.mark.parametrize(
    ("modele_type, _class, factory"),
    (
        (ARRETE, ModeleArrete, ModeleArreteFactory),
        (
            LETTRE,
            ModeleLettreNotification,
            ModeleLettreNotificationFactory,
        ),
    ),
)
def test_delete_modele_with_correct_perimetre(modele_type, _class, factory):
    departement_perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=departement_perimetre)
    client = ClientWithLoggedUserFactory(user)
    modele = factory(perimetre=departement_perimetre, name="Mon modèle")
    url = reverse(
        "gsl_notification:delete-modele",
        kwargs={"modele_type": modele_type, "modele_id": modele.id},
    )

    response = client.post(url)

    expected_redirect_url = reverse(
        "gsl_notification:modele-liste", args=[modele.dotation]
    )
    assert response.status_code == 302
    assert response.url == expected_redirect_url

    assert _class.objects.count() == 0
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 20
    if modele_type == ARRETE:
        assert message.message == "Le modèle d’arrêté “Mon modèle” a été supprimé."
    else:
        assert (
            message.message
            == "Le modèle de lettre de notification “Mon modèle” a été supprimé."
        )


@pytest.mark.parametrize(
    ("modele_type, factory, modele_class, modele_factory"),
    (
        (ARRETE, ArreteFactory, ModeleArrete, ModeleArreteFactory),
        (
            LETTRE,
            LettreNotificationFactory,
            ModeleLettreNotification,
            ModeleLettreNotificationFactory,
        ),
    ),
)
@pytest.mark.parametrize("protected_objects_count", [1, 3])
def test_delete_modele_with_modele_used_by_an_arrete(
    modele_type, factory, modele_class, modele_factory, protected_objects_count
):
    departement_perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=departement_perimetre)
    client = ClientWithLoggedUserFactory(user)
    modele = modele_factory(perimetre=departement_perimetre)
    factory.create_batch(protected_objects_count, modele=modele)
    url = reverse(
        "gsl_notification:delete-modele",
        kwargs={"modele_type": modele_type, "modele_id": modele.id},
    )

    response = client.post(url)

    expected_redirect_url = reverse(
        "gsl_notification:modele-liste", args=[modele.dotation]
    )
    assert response.status_code == 302
    assert response.url == expected_redirect_url

    assert modele_class.objects.count() == 1, (
        "On s'attend à ce que le ModeleArrete ne soit pas supprimé"
    )
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert message.extra_tags == "alert"
    if modele_type == ARRETE:
        if protected_objects_count == 1:
            assert (
                message.message
                == "Le modèle n'a pas été supprimé car il est utilisé par 1 arrêté."
            )
        else:
            assert (
                message.message
                == "Le modèle n'a pas été supprimé car il est utilisé par 3 arrêtés."
            )
    else:
        if protected_objects_count == 1:
            assert (
                message.message
                == "Le modèle n'a pas été supprimé car il est utilisé par 1 lettre de notification."
            )
        else:
            assert (
                message.message
                == "Le modèle n'a pas été supprimé car il est utilisé par 3 lettres de notification."
            )


@pytest.mark.parametrize(
    ("modele_type, _class, factory"),
    (
        (ARRETE, ModeleArrete, ModeleArreteFactory),
        (
            LETTRE,
            ModeleLettreNotification,
            ModeleLettreNotificationFactory,
        ),
    ),
)
def test_delete_modele_with_wrong_perimetre(modele_type, _class, factory):
    user = CollegueFactory(perimetre=PerimetreDepartementalFactory())
    client = ClientWithLoggedUserFactory(user)
    modele = factory(perimetre=PerimetreDepartementalFactory())
    url = reverse(
        "gsl_notification:delete-modele",
        kwargs={"modele_type": modele_type, "modele_id": modele.id},
    )

    response = client.post(url)

    assert response.status_code == 404

    assert _class.objects.count() == 1


@pytest.mark.parametrize(
    ("modele_type"),
    (
        ARRETE,
        LETTRE,
    ),
)
def test_delete_nonexistent_modele_arrete(client, modele_type):
    url = reverse(
        "gsl_notification:delete-modele",
        kwargs={"modele_type": modele_type, "modele_id": 99999},
    )
    response = client.post(url)
    assert response.status_code == 404
