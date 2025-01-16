import pytest

from gsl_programmation.models import SimulationProjet
from gsl_programmation.services import EnveloppeService
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    SimulationFactory,
    SimulationProjetFactory,
)


@pytest.fixture
def enveloppe():
    return DetrEnveloppeFactory()


@pytest.fixture
def simulation(enveloppe):
    return SimulationFactory.create(enveloppe=enveloppe)


@pytest.fixture
def simulation_projet1(enveloppe, simulation):
    return SimulationProjetFactory.create(
        enveloppe=enveloppe, simulation=simulation, montant=100.00
    )


@pytest.fixture
def simulation_projet2(enveloppe, simulation):
    return SimulationProjetFactory.create(
        enveloppe=enveloppe,
        simulation=simulation,
        montant=200.00,
        status=SimulationProjet.STATUS_VALID,
    )


@pytest.mark.django_db
def test_get_total_amount_validated(enveloppe, simulation_projet1, simulation_projet2):
    # Call the method
    total_amount = EnveloppeService.get_total_amount_validated(enveloppe)

    # Assert the expected result
    assert total_amount == 200.00
