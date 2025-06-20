import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_projet.tests.factories import (
    CategorieDetrFactory,
    DetrProjetFactory,
    ProjetFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_arrondissement():
    return PerimetreArrondissementFactory()


@pytest.fixture
def perimetre_departement(perimetre_arrondissement):
    return PerimetreDepartementalFactory(
        departement=perimetre_arrondissement.departement
    )


@pytest.fixture
def perimetre_region(perimetre_arrondissement):
    return PerimetreRegionalFactory(region=perimetre_arrondissement.region)


@pytest.fixture
def regional_user(perimetre_region):
    return CollegueFactory(perimetre=perimetre_region)


@pytest.fixture
def departemental_user(perimetre_departement):
    return CollegueFactory(perimetre=perimetre_departement)


def test_project_list_view_has_correct_detr_category_choices_for_departemental_user(
    departemental_user,
):
    departement = departemental_user.perimetre.departement
    client = ClientWithLoggedUserFactory(departemental_user)
    url = reverse("projet:list")

    detr_category_displayed = CategorieDetrFactory(
        annee=2025, departement=departement, is_current=True
    )
    wrong_year_category = CategorieDetrFactory(
        annee=2023, departement=departement, is_current=False
    )
    wrong_departement_category = CategorieDetrFactory(
        annee=2025, departement=DepartementFactory(), is_current=True
    )
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context["categorie_detr_choices"]) == 1
    assert detr_category_displayed in response.context["categorie_detr_choices"]
    assert all(
        category not in response.context["categorie_detr_choices"]
        for category in (wrong_departement_category, wrong_year_category)
    )


def test_project_list_view_has_previous_year_category_choices_if_needed(
    departemental_user,
):
    departement = departemental_user.perimetre.departement
    client = ClientWithLoggedUserFactory(departemental_user)
    url = reverse("projet:list")

    # should display most recent detr category in the right departement
    detr_category_displayed = CategorieDetrFactory(
        annee=2023, departement=departement, is_current=True
    )
    wrong_year_category = CategorieDetrFactory(
        annee=2022, departement=departement, is_current=False
    )
    wrong_departement_category = CategorieDetrFactory(
        annee=2025,
        departement=DepartementFactory(),
        is_current=True,
    )
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context["categorie_detr_choices"]) == 1
    assert detr_category_displayed in response.context["categorie_detr_choices"]
    assert all(
        category not in response.context["categorie_detr_choices"]
        for category in (wrong_departement_category, wrong_year_category)
    )


def test_project_list_view_regional_user_does_not_see_category_detr_choices(
    regional_user,
):
    client = ClientWithLoggedUserFactory(regional_user)
    url = reverse("projet:list")
    detr_category_from_region = CategorieDetrFactory(
        annee=2025,
        departement=DepartementFactory(region=regional_user.perimetre.region),
    )

    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context["categorie_detr_choices"]) == 0
    assert detr_category_from_region not in response.context["categorie_detr_choices"]


@pytest.fixture
def categorie_detr_a(perimetre_arrondissement):
    return CategorieDetrFactory(
        id=866,
        annee=2025,
        departement=perimetre_arrondissement.departement,
        libelle="Choix A",
        rang=1,
        is_current=True,
    )


@pytest.fixture
def categorie_detr_b(perimetre_arrondissement):
    return CategorieDetrFactory(
        id=867,
        annee=2025,
        departement=perimetre_arrondissement.departement,
        libelle="Choix B",
        rang=2,
        is_current=True,
    )


@pytest.fixture
def categorie_detr_c(perimetre_arrondissement):
    return CategorieDetrFactory(
        annee=2025,
        departement=perimetre_arrondissement.departement,
        libelle="Choix C",
        rang=3,
        is_current=True,
    )


def projet_with_categories_detr(categories, perimetre):
    projet = ProjetFactory(perimetre=perimetre)
    dotationprojet = DetrProjetFactory(projet=projet)
    for categorie in categories:
        dotationprojet.detr_categories.add(categorie)
    dotationprojet.save()
    return projet


def test_filter_project_list_on_category_detr(
    perimetre_arrondissement,
    perimetre_departement,
    departemental_user,
    categorie_detr_a,
    categorie_detr_b,
    categorie_detr_c,
):
    projet_with_both_categories = projet_with_categories_detr(
        [categorie_detr_a, categorie_detr_b], perimetre_arrondissement
    )
    projet_with_category_a = projet_with_categories_detr(
        [categorie_detr_a, CategorieDetrFactory()], perimetre_arrondissement
    )
    projet_with_category_b = projet_with_categories_detr(
        [categorie_detr_b, CategorieDetrFactory()], perimetre_arrondissement
    )

    client = ClientWithLoggedUserFactory(departemental_user)
    url = reverse("projet:list")

    response = client.get(
        url,
        data={"categorie_detr": [str(categorie_detr_a.id), str(categorie_detr_c.id)]},
    )

    assert response.status_code == 200

    assert (
        response.context["categorie_detr_placeholder"]
        == f"{categorie_detr_a.libelle}, {categorie_detr_c.libelle}"
    )

    object_list = set(response.context["object_list"])
    assert projet_with_both_categories in object_list
    assert projet_with_category_a in object_list
    assert projet_with_category_b not in object_list
