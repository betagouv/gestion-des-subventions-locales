import pytest

from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def simulation() -> Simulation:
    return SimulationFactory()


@pytest.fixture
def simulation_projects(simulation):
    SimulationProjetFactory.create_batch(
        2,
        simulation=simulation,
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory(
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory.create_batch(
        3,
        simulation=simulation,
        status=SimulationProjet.STATUS_REFUSED,
    )
    SimulationProjetFactory.create_batch(
        1,
        simulation=simulation,
        status=SimulationProjet.STATUS_PROCESSING,
    )


@pytest.mark.django_db
def test_get_projet_status_summary(simulation, simulation_projects):
    summary = simulation.get_projet_status_summary()

    expected_summary = {
        SimulationProjet.STATUS_REFUSED: 3,
        SimulationProjet.STATUS_PROCESSING: 1,
        SimulationProjet.STATUS_ACCEPTED: 2,
        SimulationProjet.STATUS_PROVISOIRE: 0,
        "notified": 0,
    }

    assert summary == expected_summary
