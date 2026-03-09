import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_simulation.tests.factories import SimulationFactory

pytestmark = pytest.mark.django_db


class TestSimulationRenameView:
    def test_get_displays_form(self):
        enveloppe = DetrEnveloppeFactory()
        simulation = SimulationFactory(enveloppe=enveloppe)
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        url = reverse("simulation:simulation-rename", args=[simulation.id])
        response = client.get(url)

        assert response.status_code == 200
        assert "form" in response.context

    def test_rename_simulation_success(self):
        enveloppe = DetrEnveloppeFactory()
        simulation = SimulationFactory(enveloppe=enveloppe)
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        url = reverse("simulation:simulation-rename", args=[simulation.id])
        response = client.post(url, {"title": "Nouveau titre"}, follow=True)

        assert response.status_code == 200
        simulation.refresh_from_db()
        assert simulation.title == "Nouveau titre"
        assert response.request["PATH_INFO"] == simulation.get_absolute_url()

    def test_rename_simulation_redirects_to_next_url(self):
        enveloppe = DetrEnveloppeFactory()
        simulation = SimulationFactory(enveloppe=enveloppe)
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        list_url = reverse("simulation:simulation-list")
        url = reverse("simulation:simulation-rename", args=[simulation.id])
        response = client.post(
            f"{url}?next={list_url}", {"title": "Nouveau titre"}, follow=True
        )

        assert response.status_code == 200
        simulation.refresh_from_db()
        assert simulation.title == "Nouveau titre"
        assert response.request["PATH_INFO"] == list_url

    def test_rename_simulation_ignores_unsafe_next_url(self):
        enveloppe = DetrEnveloppeFactory()
        simulation = SimulationFactory(enveloppe=enveloppe)
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        url = reverse("simulation:simulation-rename", args=[simulation.id])
        response = client.post(
            f"{url}?next=https://evil.com", {"title": "Nouveau titre"}, follow=True
        )

        assert response.status_code == 200
        simulation.refresh_from_db()
        assert simulation.title == "Nouveau titre"
        assert response.request["PATH_INFO"] == simulation.get_absolute_url()

    def test_rename_simulation_returns_404_when_not_visible(self):
        enveloppe = DetrEnveloppeFactory()
        simulation = SimulationFactory(enveloppe=enveloppe, title="Original")
        other_user = CollegueFactory()
        client = ClientWithLoggedUserFactory(other_user)

        url = reverse("simulation:simulation-rename", args=[simulation.id])
        response = client.post(url, {"title": "Nouveau titre"})

        assert response.status_code == 404
        simulation.refresh_from_db()
        assert simulation.title == "Original"
