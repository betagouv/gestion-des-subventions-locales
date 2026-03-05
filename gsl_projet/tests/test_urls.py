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
def test_missing_annotations_list(client_with_55_user_logged):
    url = reverse("projet:missing-annotations-list")
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_projet_detail_visible_by_user_with_correct_perimetre(
    client_with_55_user_logged, projets_from_55
):
    projet = projets_from_55[0]
    url = reverse("projet:get-projet", args=[projet.id])
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200
    assertTemplateUsed(response, "gsl_projet/projet.html")


@pytest.mark.django_db
def test_projet_notes_tab_uses_the_right_template(
    client_with_55_user_logged, projets_from_55
):
    projet = projets_from_55[0]
    url = reverse("projet:get-projet-notes", args=[projet.id])
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200
    assertTemplateUsed(response, "gsl_projet/projet/tab_notes.html")
    assertTemplateUsed(response, "gsl_projet/projet.html")


@pytest.mark.django_db
def test_projet_notes_tab_has_comment_cards(
    client_with_55_user_logged, projets_from_55
):
    """L'onglet notes inclut les comment_cards dans le contexte."""
    projet = projets_from_55[0]
    url = reverse("projet:get-projet-notes", args=[projet.id])
    response = client_with_55_user_logged.get(url, follow=True)
    assert response.status_code == 200
    assert "comment_cards" in response.context
    assert len(response.context["comment_cards"]) == 3


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


@pytest.mark.django_db
def test_projet_comment_cannot_be_updated_when_projet_outside_user_perimetre(
    client_with_55_user_logged, projets_from_88
):
    """Un utilisateur ne peut pas modifier les commentaires d'un projet hors de son périmètre."""
    projet = projets_from_88[0]
    original_comment = "Commentaire initial"
    projet.comment_1 = original_comment
    projet.save(update_fields=["comment_1"])

    url = reverse("projet:update-projet-comment", args=[projet.id])
    response = client_with_55_user_logged.post(
        url,
        data={"comment_number": "1", "value": "Tentative de modification"},
        follow=True,
    )

    assert response.status_code == 404
    projet.refresh_from_db()
    assert projet.comment_1 == original_comment


@pytest.mark.django_db
def test_projet_comment_update_redirects_to_next_url(
    client_with_55_user_logged, projets_from_55
):
    """Après mise à jour, redirection vers l'URL passée en paramètre next."""
    projet = projets_from_55[0]
    notes_url = reverse("projet:get-projet-notes", args=[projet.id])
    update_url = reverse("projet:update-projet-comment", args=[projet.id])

    response = client_with_55_user_logged.post(
        update_url,
        data={
            "comment_number": "1",
            "value": "Nouveau commentaire",
            "next": notes_url,
        },
        follow=True,
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "gsl_projet/projet/tab_notes.html")
    projet.refresh_from_db()
    assert projet.comment_1 == "Nouveau commentaire"


@pytest.mark.django_db
def test_projet_comment_update_redirects_to_notes_when_next_invalid(
    client_with_55_user_logged, projets_from_55
):
    """Avec un next externe ou invalide, redirection vers l'onglet notes projet."""
    projet = projets_from_55[0]
    update_url = reverse("projet:update-projet-comment", args=[projet.id])
    expected_redirect = reverse("projet:get-projet-notes", args=[projet.id])

    response = client_with_55_user_logged.post(
        update_url,
        data={
            "comment_number": "1",
            "value": "Commentaire",
            "next": "https://evil.com/phishing",
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.url == expected_redirect
