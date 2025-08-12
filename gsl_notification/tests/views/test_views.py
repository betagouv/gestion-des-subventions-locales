from unittest.mock import MagicMock, patch

import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from freezegun import freeze_time

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreFactory,
    PerimetreRegionalFactory,
)
from gsl_notification.models import Arrete, LettreNotification
from gsl_notification.tests.factories import (
    ArreteFactory,
    ArreteSigneFactory,
    LettreNotificationFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import ARRETE, DOTATION_DETR, DOTATION_DSIL, LETTRE

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


#### select-modele -----------------------------------

####### Without correct perimetre


@pytest.mark.parametrize(
    "modele_factory, document_type",
    (
        (ModeleArreteFactory, ARRETE),
        (ModeleLettreNotificationFactory, LETTRE),
    ),
)
def test_get_select_modele_gives_correct_perimetre_and_dotation_modele(
    modele_factory, document_type
):
    # Périmètres
    arrondissement_11 = PerimetreArrondissementFactory()
    departement_1 = PerimetreDepartementalFactory(
        departement=arrondissement_11.departement, region=arrondissement_11.region
    )
    region = PerimetreRegionalFactory(region=departement_1.region)
    arrondissement_12 = PerimetreArrondissementFactory(
        arrondissement__departement=departement_1.departement,
        departement=departement_1.departement,
        region=region.region,
    )

    departement_2 = PerimetreDepartementalFactory(
        departement__region=region.region, region=region.region
    )
    _arrondissement_21 = PerimetreArrondissementFactory(
        arrondissement__departement=departement_2.departement,
        region=region.region,
        departement=departement_2.departement,
    )

    # Modèles DETR
    _detr_modele_arr_11 = modele_factory(
        dotation=DOTATION_DETR, perimetre=arrondissement_11
    )
    detr_modele_dep_1 = modele_factory(dotation=DOTATION_DETR, perimetre=departement_1)
    _detr_modele_arr_12 = modele_factory(
        dotation=DOTATION_DETR, perimetre=arrondissement_12
    )
    _detr_modele_dep_2 = modele_factory(dotation=DOTATION_DETR, perimetre=departement_2)
    _detr_modele__arr_21 = modele_factory(
        dotation=DOTATION_DETR, perimetre=_arrondissement_21
    )

    # Modèles DSIL
    _dsil_modele_arr_11 = modele_factory(
        dotation=DOTATION_DSIL, perimetre=arrondissement_11
    )
    _dsil_modele_dep_1 = modele_factory(dotation=DOTATION_DSIL, perimetre=departement_1)
    _dsil_modele_reg = modele_factory(dotation=DOTATION_DSIL, perimetre=region)
    _dsil_modele_arr_12 = modele_factory(
        dotation=DOTATION_DSIL, perimetre=arrondissement_12
    )
    _dsil_modele_dep_2 = modele_factory(dotation=DOTATION_DSIL, perimetre=departement_2)
    _dsil_modele__arr_21 = modele_factory(
        dotation=DOTATION_DSIL, perimetre=_arrondissement_21
    )

    programmation_projet = ProgrammationProjetFactory(
        dotation_projet__dotation=DOTATION_DETR,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        dotation_projet__projet__perimetre=departement_1,
    )

    user = CollegueFactory(perimetre=departement_1)
    client = ClientWithLoggedUserFactory(user)

    url = reverse(
        "notification:select-modele",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    response = client.get(url)
    assert len(response.context["modeles_list"]) == 1, (
        "Seul le modèle avec le bon périmètre doit être proposé"
    )
    assert response.context["modeles_list"][0] == {
        "actions": [
            {
                "href": f"/notification/{programmation_projet.id}/modifier-document/{document_type}?modele_id={detr_modele_dep_1.id}",
                "label": "Sélectionner",
            },
        ],
        "description": detr_modele_dep_1.description,
        "name": detr_modele_dep_1.name,
    }
    assert (
        url
        == f"/notification/{programmation_projet.id}/selection-d-un-modele/{document_type}"
    )


### modifier-document -----------------------------------

##### GET

####### Without correct perimetre


@pytest.mark.parametrize(
    "factory, document_type",
    (
        (ArreteFactory, ARRETE),
        (LettreNotificationFactory, LETTRE),
    ),
)
@pytest.mark.parametrize(
    "with_document_already_created",
    (False, True),
)
def test_modify_arrete_url_with_not_correct_perimetre(
    programmation_projet,
    different_perimetre_client_with_user_logged,
    factory,
    document_type,
    with_document_already_created,
):
    if with_document_already_created:
        factory(
            programmation_projet=programmation_projet,
            content="<p>Contenu de l’arrêté</p>",
        )
    else:
        assert not hasattr(programmation_projet, "arrete")
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    assert (
        url
        == f"/notification/{programmation_projet.id}/modifier-document/{document_type}"
    )
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


####### Without modele_id
######### Without an existing document


@pytest.mark.parametrize("document_type", (ARRETE, LETTRE))
def test_modify_document_url_without_arrete(
    programmation_projet, correct_perimetre_client_with_user_logged, document_type
):
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    assert (
        url
        == f"/notification/{programmation_projet.id}/modifier-document/{document_type}"
    )
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


######### With an existing document


@pytest.mark.parametrize(
    "document_type, factory",
    ((ARRETE, ArreteFactory), (LETTRE, LettreNotificationFactory)),
)
def test_modify_arrete_url_with_arrete(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    factory,
):
    document = factory(
        programmation_projet=programmation_projet, content="<p>Contenu de l’arrêté</p>"
    )
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    assert (
        url
        == f"/notification/{programmation_projet.id}/modifier-document/{document_type}"
    )
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert response.context["arrete_initial_content"] == "<p>Contenu de l’arrêté</p>"
    if document_type == ARRETE:
        assert response.context["page_title"] == "Modification de l'arrêté attributif"
    else:
        assert (
            response.context["page_title"]
            == "Modification de la lettre de notification"
        )
    assert response.context["modele"] == document.modele
    assert response.templates[0].name == "gsl_notification/change_document.html"


####### With modele_id
######### Without an existing document
########### With correct modele_perimetre


@pytest.mark.parametrize(
    "document_type, modele_factory",
    ((ARRETE, ModeleArreteFactory), (LETTRE, ModeleLettreNotificationFactory)),
)
def test_modify_arrete_url_without_document_and_with_modele_id(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    modele_factory,
):
    modele = modele_factory(
        perimetre=correct_perimetre_client_with_user_logged.user.perimetre,
        dotation=programmation_projet.dotation_projet.dotation,
    )
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    data = {"modele_id": modele.id}
    assert (
        url
        == f"/notification/{programmation_projet.id}/modifier-document/{document_type}"
    )
    response = correct_perimetre_client_with_user_logged.get(url, data)
    assert response.status_code == 200
    assert response.context["arrete_initial_content"] == modele.content
    if document_type == ARRETE:
        assert response.context["page_title"] == "Création de l'arrêté attributif"
    else:
        assert response.context["page_title"] == "Création de la lettre de notification"
    assert response.context["modele"] == modele
    assert response.templates[0].name == "gsl_notification/change_document.html"


########### With wrong modele_perimetre


@pytest.mark.parametrize(
    "document_type, modele_factory",
    ((ARRETE, ModeleArreteFactory), (LETTRE, ModeleLettreNotificationFactory)),
)
def test_modify_arrete_url_without_document_and_with_wrong_modele_id(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    modele_factory,
):
    modele = modele_factory(
        dotation=programmation_projet.dotation_projet.dotation,
    )

    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    data = {"modele_id": modele.id}
    assert (
        url
        == f"/notification/{programmation_projet.id}/modifier-document/{document_type}"
    )
    response = correct_perimetre_client_with_user_logged.get(url, data)
    assert response.status_code == 404


######### With an existing document
########### With correct dotation


@pytest.mark.parametrize(
    "document_type, factory, modele_factory",
    (
        (ARRETE, ArreteFactory, ModeleArreteFactory),
        (LETTRE, LettreNotificationFactory, ModeleLettreNotificationFactory),
    ),
)
def test_modify_arrete_url_with_document_and_with_correct_modele_id(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    factory,
    modele_factory,
):
    modele = modele_factory(
        perimetre=correct_perimetre_client_with_user_logged.user.perimetre,
        dotation=programmation_projet.dotation_projet.dotation,
    )
    factory(
        programmation_projet=programmation_projet, content="<p>Contenu de l’arrêté</p>"
    )
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    data = {"modele_id": modele.id}
    assert (
        url
        == f"/notification/{programmation_projet.id}/modifier-document/{document_type}"
    )
    response = correct_perimetre_client_with_user_logged.get(url, data=data)
    assert response.status_code == 200
    assert response.context["arrete_initial_content"] == "<p>Contenu du modèle</p>"
    if document_type == ARRETE:
        expected_title = "Modification de l'arrêté attributif"
    else:
        expected_title = "Modification de la lettre de notification"
    assert response.context["page_title"] == expected_title
    assert response.context["modele"] == modele
    assert response.templates[0].name == "gsl_notification/change_document.html"


########### With wrong dotation


@pytest.mark.parametrize(
    "document_type, factory, modele_factory",
    (
        (ARRETE, ArreteFactory, ModeleArreteFactory),
        (LETTRE, LettreNotificationFactory, ModeleLettreNotificationFactory),
    ),
)
def test_modify_arrete_url_with_document_and_with_wrong_modele_id(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    factory,
    modele_factory,
):
    modele = modele_factory(
        perimetre=correct_perimetre_client_with_user_logged.user.perimetre,
        dotation="DSIL"
        if programmation_projet.dotation_projet.dotation == "DETR"
        else "DETR",
    )
    factory(
        programmation_projet=programmation_projet, content="<p>Contenu de l’arrêté</p>"
    )
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    data = {"modele_id": modele.id}
    assert (
        url
        == f"/notification/{programmation_projet.id}/modifier-document/{document_type}"
    )
    response = correct_perimetre_client_with_user_logged.get(url, data=data)
    assert response.status_code == 404


##### POST


@pytest.mark.parametrize(
    "document_type",
    (ARRETE, LETTRE),
)
def test_change_document_view_valid_but_with_wrong_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged, document_type
):
    assert not hasattr(programmation_projet, "arrete")
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    data = {
        "created_by": different_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
        "content": "<p>Le contenu</p>",
    }
    response = different_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 404
    assert not hasattr(programmation_projet, document_type)


@freeze_time("2025-08-11")
@pytest.mark.parametrize(
    "document_type, document_model, modele_factory",
    (
        (ARRETE, Arrete, ModeleArreteFactory),
        (LETTRE, LettreNotification, ModeleLettreNotificationFactory),
    ),
)
def test_change_document_view_valid_without_existing_document(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    document_model,
    modele_factory,
):
    modele = modele_factory(
        dotation=programmation_projet.dotation,
        perimetre=programmation_projet.projet.perimetre,
    )
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    url += f"?modele_id={modele.id}"
    data = {
        "created_by": correct_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
        "content": "<p>Le contenu</p>",
        "modele": modele.id,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 302
    assert response["Location"] == f"/notification/{programmation_projet.id}/documents/"
    assert document_model.objects.count() == 1
    document = document_model.objects.first()
    assert document.content == "<p>Le contenu</p>"
    assert document.created_by == correct_perimetre_client_with_user_logged.user
    assert document.programmation_projet == programmation_projet
    assert document.modele == modele
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 20
    if document_type == ARRETE:
        assert (
            message.message
            == "L'arrêté “arrêté-attributif-2025-08-11.pdf” a bien été créé."
        )
    else:
        assert (
            message.message
            == "La lettre de notification “lettre-notification-2025-08-11.pdf” a bien été créée."
        )


@freeze_time("2025-08-11")
@pytest.mark.parametrize(
    "document_type, factory, modele_factory",
    (
        (ARRETE, ArreteFactory, ModeleArreteFactory),
        (LETTRE, LettreNotificationFactory, ModeleLettreNotificationFactory),
    ),
)
def test_change_document_view_valid_with_existing_document(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    factory,
    modele_factory,
):
    document = factory(
        programmation_projet=programmation_projet, content="<p>Ancien contenu</p>"
    )
    new_modele = modele_factory()
    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    data = {
        "created_by": correct_perimetre_client_with_user_logged.user.id,
        "programmation_projet": programmation_projet.id,
        "content": "<p>Le contenu</p>",
        "modele": new_modele.id,
    }
    response = correct_perimetre_client_with_user_logged.post(url, data)
    assert response.status_code == 302
    assert response["Location"] == f"/notification/{programmation_projet.id}/documents/"
    document.refresh_from_db()
    assert document.content == "<p>Le contenu</p>"
    assert document.created_by == correct_perimetre_client_with_user_logged.user
    assert document.programmation_projet == programmation_projet
    assert document.modele == new_modele
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 20
    if document_type == ARRETE:
        assert (
            message.message
            == "L'arrêté “arrêté-attributif-2025-08-11.pdf” a bien été modifié."
        )
    else:
        assert (
            message.message
            == "La lettre de notification “lettre-notification-2025-08-11.pdf” a bien été modifiée."
        )


@pytest.mark.parametrize(
    "document_type, factory",
    (
        (ARRETE, ArreteFactory),
        (LETTRE, LettreNotificationFactory),
    ),
)
def test_change_document_view_invalid(
    programmation_projet,
    correct_perimetre_client_with_user_logged,
    document_type,
    factory,
):
    factory(programmation_projet=programmation_projet, content="<p>Ancien contenu</p>")

    url = reverse(
        "notification:modifier-document",
        kwargs={
            "programmation_projet_id": programmation_projet.id,
            "document_type": document_type,
        },
    )
    response = correct_perimetre_client_with_user_logged.post(url, {})
    assert response.status_code == 200
    assert response.context["arrete_form"].errors == {
        "created_by": ["Ce champ est obligatoire."],
        "programmation_projet": ["Ce champ est obligatoire."],
        "modele": ["Ce champ est obligatoire."],
        "content": ["Ce champ est obligatoire."],
    }
    assert response.templates[0].name == "gsl_notification/change_document.html"
    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1
    message = list(messages)[0]
    assert message.level == 40
    assert message.message == "Erreur dans le formulaire"


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


### arrete-view


def test_arrete_view_url_with_correct_perimetre(
    programmation_projet, correct_perimetre_client_with_user_logged
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("notification:arrete-view", kwargs={"arrete_id": arrete.id})
    assert url == f"/notification/arrete/{arrete.id}/view/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_arrete_view_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged,
):
    url = reverse("notification:arrete-view", kwargs={"arrete_id": 1000})
    assert url == "/notification/arrete/1000/view/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_arrete_view_url_with_wrong_perimetre(
    programmation_projet, different_perimetre_client_with_user_logged
):
    arrete = ArreteFactory(programmation_projet=programmation_projet)
    url = reverse("notification:arrete-view", kwargs={"arrete_id": arrete.id})
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


# ArreteSigne

### create-arrete-signe -----------------------------


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
    url = arrete_signe.get_download_url()
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


def test_arrete_signe_download_url_without_correct_perimetre_and_without_arrete(
    arrete_signe, different_perimetre_client_with_user_logged
):
    url = arrete_signe.get_download_url()
    assert url == f"/notification/arrete-signe/{arrete_signe.id}/download/"
    response = different_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


### arrete-signe-view


def test_arrete_signe_view_url_with_correct_perimetre_and_without_arrete(
    correct_perimetre_client_with_user_logged,
):
    url = reverse(
        "notification:arrete-signe-view",
        kwargs={"arrete_signe_id": 1000},
    )
    assert url == "/notification/arrete-signe/1000/view/"
    response = correct_perimetre_client_with_user_logged.get(url)
    assert response.status_code == 404


def test_arrete_signe_view_url_without_correct_perimetre_and_without_arrete(
    arrete_signe, different_perimetre_client_with_user_logged
):
    url = arrete_signe.get_view_url()
    assert url == f"/notification/arrete-signe/{arrete_signe.id}/view/"
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
