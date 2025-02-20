from decimal import Decimal

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
)
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def client_with_user_logged():
    user = CollegueFactory()
    return ClientWithLoggedUserFactory(user)


@pytest.mark.django_db
def test_simulation_list_url(client_with_user_logged):
    url = reverse("simulation:simulation-list")
    response = client_with_user_logged.get(url, follow=True)
    assert response.status_code == 200


@pytest.mark.django_db
def test_simulation_detail_url(client_with_user_logged):
    SimulationFactory(slug="test-slug")

    url = reverse("simulation:simulation-detail", kwargs={"slug": "test-slug"})
    response = client_with_user_logged.get(url)
    assert response.status_code == 200


@pytest.fixture
def cote_d_or():
    return DepartementFactory()


@pytest.fixture
def client_with_cote_d_or_user_logged(cote_d_or):
    cote_d_or_perimetre = PerimetreDepartementalFactory(departement=cote_d_or)
    cote_dorien_collegue = CollegueFactory(perimetre=cote_d_or_perimetre)
    return ClientWithLoggedUserFactory(cote_dorien_collegue)


@pytest.fixture
def cote_dorien_simulation_projet(cote_d_or):
    projet = ProjetFactory(demandeur__arrondissement__departement=cote_d_or)
    return SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_PROVISOIRE, taux=0, montant=0
    )


expected_status_summary = {
    "cancelled": 0,
    "draft": 0,
    "notified": 0,
    "provisoire": 1,
    "valid": 0,
}


@pytest.mark.django_db
def test_patch_taux_simulation_projet_url(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="taux=0.5", follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_detail.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("0.00")
    assert response.context["filter_params"] == ""

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.taux == 0.5


@pytest.mark.django_db
def test_patch_taux_simulation_projet_url_with_htmx(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="taux=0.5", headers={"HX-Request": "true"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("0.00")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.taux == 0.5


@pytest.mark.django_db
def test_patch_montant_simulation_projet_url(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="montant=100", follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_detail.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("100")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.montant == 100


@pytest.mark.django_db
def test_patch_montant_simulation_projet_url_with_htmx(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="montant=100", headers={"HX-Request": "true"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("100")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.montant == 100


status_update_expected_status_summary = {
    "cancelled": 0,
    "draft": 0,
    "notified": 0,
    "provisoire": 0,
    "valid": 1,
}


@pytest.mark.django_db
def test_patch_status_simulation_projet_url(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="status=valid", follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "gsl_simulation/simulation_detail.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == status_update_expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("0")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_patch_status_simulation_projet_url_with_htmx(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="status=valid", headers={"HX-Request": "true"}, follow=True
    )
    assert response.status_code == 200
    assert response.templates[0].name == "htmx/projet_update.html"
    assert response.context["simu"] == cote_dorien_simulation_projet
    assert response.context["projet"] == cote_dorien_simulation_projet.projet
    assert response.context["available_states"] == SimulationProjet.STATUS_CHOICES
    assert response.context["status_summary"] == status_update_expected_status_summary
    assert response.context["total_amount_granted"] == Decimal("0")

    cote_dorien_simulation_projet.refresh_from_db()
    assert cote_dorien_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_simulation_form_url(client_with_user_logged):
    url = reverse("simulation:simulation-form")
    response = client_with_user_logged.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_patch_projet_only_if_projet_is_included_in_user_perimetre(
    client_with_cote_d_or_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="taux=0.5", follow=True
    )
    assert response.status_code == 200

    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="montant=400", follow=True
    )
    assert response.status_code == 200

    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_cote_d_or_user_logged.patch(
        url, data="status=valid", follow=True
    )
    assert response.status_code == 200


@pytest.fixture
def client_with_iconnais_user_logged():
    yonne = DepartementFactory()
    yonne_perimetre = PerimetreDepartementalFactory(departement=yonne)
    icaunais_collegue = CollegueFactory(perimetre=yonne_perimetre)
    return ClientWithLoggedUserFactory(icaunais_collegue)


@pytest.mark.django_db
def test_cant_patch_projet_only_if_projet_is_not_included_in_user_perimetre(
    client_with_iconnais_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.patch(url, data="taux=0.5")
    assert response.status_code == 404

    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.patch(url, data="montant=400")
    assert response.status_code == 404

    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_iconnais_user_logged.patch(url, data="status=valid")
    assert response.status_code == 404


@pytest.fixture
def client_with_staff_user_logged():
    staff_user = CollegueFactory(is_staff=True)
    return ClientWithLoggedUserFactory(staff_user)


@pytest.mark.django_db
def test_patch_projet_allowed_for_staff_user(
    client_with_staff_user_logged, cote_dorien_simulation_projet
):
    url = reverse(
        "simulation:patch-simulation-projet-taux",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_staff_user_logged.patch(url, data="taux=0.5", follow=True)
    assert response.status_code == 200

    url = reverse(
        "simulation:patch-simulation-projet-montant",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_staff_user_logged.patch(url, data="montant=400", follow=True)
    assert response.status_code == 200

    url = reverse(
        "simulation:patch-simulation-projet-status",
        kwargs={"pk": cote_dorien_simulation_projet.pk},
    )
    response = client_with_staff_user_logged.patch(
        url, data="status=valid", follow=True
    )
    assert response.status_code == 200
