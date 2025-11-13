import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_simulation.models import Simulation
from gsl_simulation.tests.factories import SimulationFactory

pytestmark = pytest.mark.django_db


class TestSimulationCreateView:
    def test_create_simulation_success_with_valid_data(self):
        # Arrange: a user with access to an enveloppe
        enveloppe = DetrEnveloppeFactory()
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: submit the form with valid data
        url = reverse("gsl_simulation:simulation-form")
        data = {
            "title": "My Test Simulation",
            "enveloppe": enveloppe.id,
        }
        response = client.post(url, data, follow=True)

        # Assert: simulation created and redirected to list
        assert response.status_code == 200
        assert response.request["PATH_INFO"] == reverse("simulation:simulation-list")

        simulation = Simulation.objects.get(title="My Test Simulation")
        assert simulation.created_by == user
        assert simulation.enveloppe == enveloppe

    def test_create_simulation_sets_created_by_to_authenticated_user(self):
        # Arrange: create an enveloppe and user
        enveloppe = DetrEnveloppeFactory()
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: create a simulation
        url = reverse("gsl_simulation:simulation-form")
        data = {
            "title": "Another Simulation",
            "enveloppe": enveloppe.id,
        }
        client.post(url, data)

        # Assert: created_by is the authenticated user
        simulation = Simulation.objects.get(title="Another Simulation")
        assert simulation.created_by == user

    def test_create_simulation_generates_unique_slug(self):
        # Arrange: create a simulation with a title
        enveloppe = DetrEnveloppeFactory()
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        SimulationFactory(title="My Simulation", enveloppe=enveloppe, created_by=user)

        client = ClientWithLoggedUserFactory(user)

        # Act: create another simulation with the same title
        url = reverse("gsl_simulation:simulation-form")
        data = {
            "title": "My Simulation",
            "enveloppe": enveloppe.id,
        }
        client.post(url, data)

        # Assert: both simulations exist with different slugs
        simulations = Simulation.objects.filter(title="My Simulation")
        assert simulations.count() == 2
        slugs = [sim.slug for sim in simulations]
        assert len(set(slugs)) == 2  # Both slugs are unique

    def test_create_simulation_form_shows_only_visible_envelopes(self):
        # Arrange: create two envelopes, only one visible to the user
        visible_enveloppe = DetrEnveloppeFactory()
        invisible_enveloppe = DetrEnveloppeFactory()

        user = CollegueFactory(perimetre=visible_enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: get the create view
        url = reverse("gsl_simulation:simulation-form")
        response = client.get(url)

        # Assert: only the visible enveloppe is in the form choices
        assert response.status_code == 200
        enveloppe_field = response.context["form"].fields["enveloppe"]
        enveloppe_ids = [e.id for e in enveloppe_field.queryset]

        assert visible_enveloppe.id in enveloppe_ids
        assert invisible_enveloppe.id not in enveloppe_ids

    def test_create_simulation_with_delegated_envelope(self):
        # Arrange: create an enveloppe delegated to a user's perimetre
        parent_enveloppe = DetrEnveloppeFactory()
        delegated_enveloppe = DetrEnveloppeFactory(deleguee_by=parent_enveloppe)

        user = CollegueFactory(perimetre=parent_enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: get the create view
        url = reverse("gsl_simulation:simulation-form")
        response = client.get(url)

        # Assert: both envelopes are visible to the user
        enveloppe_field = response.context["form"].fields["enveloppe"]
        enveloppe_ids = [e.id for e in enveloppe_field.queryset]

        assert parent_enveloppe.id in enveloppe_ids
        assert delegated_enveloppe.id in enveloppe_ids

    def test_create_simulation_requires_title(self):
        # Arrange: create an enveloppe and user
        enveloppe = DetrEnveloppeFactory()
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: submit form without title
        url = reverse("gsl_simulation:simulation-form")
        data = {
            "title": "",
            "enveloppe": enveloppe.id,
        }
        response = client.post(url, data)

        # Assert: form is invalid and no simulation created
        assert response.status_code == 200
        assert "form" in response.context
        assert response.context["form"].errors
        assert not Simulation.objects.filter(enveloppe=enveloppe).exists()

    def test_create_simulation_requires_enveloppe(self):
        # Arrange: create a user
        user = CollegueFactory()
        client = ClientWithLoggedUserFactory(user)

        # Act: submit form without enveloppe
        url = reverse("gsl_simulation:simulation-form")
        data = {
            "title": "My Simulation",
            "enveloppe": "",
        }
        response = client.post(url, data)

        # Assert: form is invalid and no simulation created
        assert response.status_code == 200
        assert "form" in response.context
        assert response.context["form"].errors
        assert not Simulation.objects.filter(title="My Simulation").exists()

    def test_create_simulation_view_context_data(self):
        # Arrange: create a user and enveloppe
        enveloppe = DetrEnveloppeFactory()
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: get the create view
        url = reverse("gsl_simulation:simulation-form")
        response = client.get(url)

        # Assert: context has breadcrumb and title
        assert response.status_code == 200
        assert "breadcrumb_dict" in response.context
        assert "title" in response.context

        breadcrumb = response.context["breadcrumb_dict"]
        assert breadcrumb["current"] == "Création d'une simulation de programmation"
        assert breadcrumb["links"]
        assert "Mes simulations de programmation" in breadcrumb["links"][0]["title"]

    def test_create_simulation_cannot_use_invisible_envelope(self):
        # Arrange: create two users with different perimetres and envelopes
        visible_enveloppe = DetrEnveloppeFactory()
        invisible_enveloppe = DetrEnveloppeFactory()

        user = CollegueFactory(perimetre=visible_enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: try to create simulation with invisible enveloppe
        url = reverse("gsl_simulation:simulation-form")
        data = {
            "title": "Attempt Simulation",
            "enveloppe": invisible_enveloppe.id,
        }
        response = client.post(url, data)

        # Assert: form is invalid (invalid choice)
        assert response.status_code == 200
        assert response.context["form"].errors
        assert not Simulation.objects.filter(title="Attempt Simulation").exists()

    def test_create_simulation_with_special_characters_in_title(self):
        # Arrange: create a user and enveloppe
        enveloppe = DetrEnveloppeFactory()
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: create simulation with special characters
        url = reverse("gsl_simulation:simulation-form")
        title_with_special_chars = "Simulation 2024 - Projet (test) & Finances"
        data = {
            "title": title_with_special_chars,
            "enveloppe": enveloppe.id,
        }
        response = client.post(url, data, follow=True)

        # Assert: simulation created successfully
        assert response.status_code == 200
        simulation = Simulation.objects.get(title=title_with_special_chars)
        assert simulation.created_by == user
