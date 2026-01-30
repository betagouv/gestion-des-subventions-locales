import pytest
from django.urls import reverse
from pytest_django.asserts import assertTemplateUsed

from gsl_core.tests.factories import (
    ClientWithLoggedStaffUserFactory,
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_projet.tests.factories import ProjetFactory


@pytest.fixture
def perimetre_departement_55():
    return PerimetreDepartementalFactory()


@pytest.fixture
def perimetre_departement_88():
    return PerimetreDepartementalFactory()


@pytest.fixture
def client_with_55_user_logged(perimetre_departement_55):
    user = CollegueFactory(perimetre=perimetre_departement_55)
    return ClientWithLoggedUserFactory(user)


@pytest.mark.django_db
def test_list(client_with_55_user_logged):
    url = reverse("projet:list")
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200


@pytest.fixture
def projets_from_55(perimetre_departement_55):
    return ProjetFactory.create_batch(3, dossier_ds__perimetre=perimetre_departement_55)


@pytest.fixture
def projets_from_88(perimetre_departement_88):
    return ProjetFactory.create_batch(5, dossier_ds__perimetre=perimetre_departement_88)


@pytest.mark.django_db
def test_list_with_only_visible_projets_for_user(
    client_with_55_user_logged, projets_from_55, projets_from_88
):
    url = reverse("projet:list")
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200
    assert response.context["object_list"].count() == 3


@pytest.mark.django_db
def test_projet_detail_visible_by_user_with_correct_perimetre(
    client_with_55_user_logged, projets_from_55
):
    projet = projets_from_55[0]
    url = reverse("projet:get-projet", args=[projet.id])
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200
    assertTemplateUsed(response, "gsl_projet/projet.html")


@pytest.mark.parametrize(
    "tab_name,template",
    (
        ("notes", "gsl_projet/projet/tab_notes.html"),
        ("historique", "gsl_projet/projet/tab_historique.html"),
    ),
)
@pytest.mark.django_db
def test_projet_tabs_use_the_right_templates(
    client_with_55_user_logged, projets_from_55, tab_name, template
):
    projet = projets_from_55[0]
    url = reverse("projet:get-projet-tab", args=[projet.id, tab_name])
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200
    assertTemplateUsed(response, template)
    assertTemplateUsed(response, "gsl_projet/projet.html")


@pytest.mark.django_db
def test_projet_tab_404_with_unknown_tab_name(
    client_with_55_user_logged, projets_from_55
):
    projet = projets_from_55[0]
    url = reverse("projet:get-projet-tab", args=[projet.id, "nothing"])
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_projet_detail_not_visible_by_user_with_incorrect_perimetre(
    client_with_55_user_logged, projets_from_88
):
    projet = projets_from_88[0]
    url = reverse("projet:get-projet", args=[projet.id])
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 404


@pytest.mark.django_db
def test_projet_detail_visible_by_staff(projets_from_88):
    client_with_staff_user = ClientWithLoggedStaffUserFactory()
    projet = projets_from_88[0]
    url = reverse("projet:get-projet", args=[projet.id])
    response = client_with_staff_user.get(url, follow=True)
    assert response.status_code == 200
