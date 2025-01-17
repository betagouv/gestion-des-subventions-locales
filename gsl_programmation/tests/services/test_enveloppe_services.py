import pytest

from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.models import SimulationProjet
from gsl_programmation.services import EnveloppeService
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    SimulationFactory,
    SimulationProjetFactory,
)
from gsl_projet.tests.factories import ProjetFactory


@pytest.fixture
def enveloppe():
    return DetrEnveloppeFactory()


@pytest.fixture
def simulation(enveloppe):
    return SimulationFactory.create(enveloppe=enveloppe)


@pytest.fixture
def simulation_projet1(enveloppe, simulation):
    projet = ProjetFactory.create(
        assiette=1000.00,
    )
    return SimulationProjetFactory.create(
        enveloppe=enveloppe, simulation=simulation, montant=100.00, projet=projet
    )


@pytest.fixture
def simulation_projet2(enveloppe, simulation):
    projet = ProjetFactory.create(
        dossier_ds=DossierFactory.create(
            finance_cout_total=2000.00,
        ),
    )
    return SimulationProjetFactory.create(
        enveloppe=enveloppe,
        simulation=simulation,
        montant=200.00,
        status=SimulationProjet.STATUS_VALID,
        projet=projet,
    )


@pytest.mark.django_db
def test_get_total_amount_validated(enveloppe, simulation_projet1, simulation_projet2):
    # Call the method
    total_amount = EnveloppeService.get_total_amount_validated(enveloppe)

    # Assert the expected result
    assert total_amount == 200.00


@pytest.mark.django_db
def test_get_total_amount_asked(enveloppe, simulation_projet1, simulation_projet2):
    # Call the method
    total_amount = EnveloppeService.get_total_amount_asked(enveloppe)

    # Assert the expected result
    assert total_amount == 3000.00
