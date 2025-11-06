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


class TestSimulationDeleteView:
    def test_delete_simulation_success_when_visible(self):
        # Arrange: a simulation in an enveloppe visible by the user
        enveloppe = DetrEnveloppeFactory()
        simulation = SimulationFactory(enveloppe=enveloppe)
        user = CollegueFactory(perimetre=enveloppe.perimetre)
        client = ClientWithLoggedUserFactory(user)

        # Act: delete via POST
        url = reverse("simulation:simulation-delete", args=[simulation.id])
        response = client.post(url, follow=True)

        # Assert: redirected to list and simulation removed
        assert response.status_code == 200
        assert response.request["PATH_INFO"] == reverse("simulation:simulation-list")
        assert not Simulation.objects.filter(id=simulation.id).exists()

    def test_delete_simulation_returns_404_when_not_visible(self):
        # Arrange: a simulation in an enveloppe not visible by the user
        enveloppe = DetrEnveloppeFactory()
        simulation = SimulationFactory(enveloppe=enveloppe)
        other_user = CollegueFactory()  # no matching perimetre
        client = ClientWithLoggedUserFactory(other_user)

        # Act: attempt deletion
        url = reverse("simulation:simulation-delete", args=[simulation.id])
        response = client.post(url)

        # Assert: 404 and object still exists
        assert response.status_code == 404
        assert Simulation.objects.filter(id=simulation.id).exists()
