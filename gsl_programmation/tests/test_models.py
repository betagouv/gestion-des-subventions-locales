import pytest

from gsl_programmation.models import Simulation, SimulationProjet
from gsl_programmation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def simulation() -> Simulation:
    return SimulationFactory()


@pytest.fixture
def simulation_projects(simulation):
    SimulationProjetFactory.create_batch(
        2,
        simulation=simulation,
        status=SimulationProjet.STATUS_VALID,
    )
    SimulationProjetFactory(
        status=SimulationProjet.STATUS_VALID,
    )
    SimulationProjetFactory.create_batch(
        3,
        simulation=simulation,
        status=SimulationProjet.STATUS_CANCELLED,
    )
    SimulationProjetFactory.create_batch(
        1,
        simulation=simulation,
        status=SimulationProjet.STATUS_DRAFT,
    )


@pytest.mark.django_db
def test_get_projet_status_summary(simulation, simulation_projects):
    summary = simulation.get_projet_status_summary()

    expected_summary = {
        SimulationProjet.STATUS_CANCELLED: 3,
        SimulationProjet.STATUS_DRAFT: 1,
        SimulationProjet.STATUS_VALID: 2,
        SimulationProjet.STATUS_PROVISOIRE: 0,
        "notified": 0,
    }

    assert summary == expected_summary
