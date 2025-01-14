import pytest
from django.urls import reverse

from gsl_core.tests.factories import RequestFactory
from gsl_programmation.models import Simulation
from gsl_programmation.tests.factories import SimulationFactory
from gsl_programmation.views import SimulationListView


@pytest.fixture
def req() -> RequestFactory:
    return RequestFactory()


@pytest.fixture
def view() -> SimulationListView:
    return SimulationListView()


@pytest.fixture
def simulations() -> list[Simulation]:
    return [SimulationFactory() for _ in range(3)]


@pytest.mark.django_db
def test_simulation_view_status_code(req, view, simulations):
    url = reverse("programmation:simulation_list")
    view.object_list = simulations
    view.request = req.get(url)

    assert view.get_queryset().count() == 3
