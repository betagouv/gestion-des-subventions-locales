import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
    RequestFactory,
)
from gsl_programmation.models import Simulation
from gsl_programmation.tests.factories import DetrEnveloppeFactory, SimulationFactory
from gsl_programmation.views import SimulationListView


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def req(perimetre_departemental) -> RequestFactory:
    user = CollegueFactory(perimetre=perimetre_departemental)
    return RequestFactory(user=user)


@pytest.fixture
def view() -> SimulationListView:
    return SimulationListView()


@pytest.fixture
def simulations(perimetre_departemental) -> list[Simulation]:
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre_departemental)
    SimulationFactory(enveloppe=enveloppe)
    SimulationFactory(enveloppe=enveloppe)
    SimulationFactory()


@pytest.mark.django_db
def test_simulation_view_status_code(req, view, simulations):
    url = reverse("programmation:simulation_list")
    view.object_list = simulations
    view.request = req.get(url)

    assert view.get_queryset().count() == 2
