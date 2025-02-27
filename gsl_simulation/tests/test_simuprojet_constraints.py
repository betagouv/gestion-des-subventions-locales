import pytest
from django.db.utils import IntegrityError

from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def simulation():
    return SimulationFactory()


@pytest.mark.django_db
def test_projet_only_once_per_simulation_and_enveloppe(simulation):
    simulation_projet_un = SimulationProjetFactory(
        simulation=simulation,
        projet=ProjetFactory(),
    )
    with pytest.raises(IntegrityError):
        SimulationProjet.objects.create(
            simulation=simulation_projet_un.simulation,
            projet=simulation_projet_un.projet,
        )


@pytest.mark.django_db
def test_projet_twice_per_simulation_with_different_projet(simulation):
    SimulationProjetFactory(
        simulation=simulation,
        projet=ProjetFactory(),
    )
    SimulationProjetFactory(simulation=simulation)


@pytest.mark.django_db
def test_projet_twice_per_simulation_with_different_simulation():
    simulation_projet = SimulationProjetFactory(
        projet=ProjetFactory(),
    )
    SimulationProjetFactory(projet=simulation_projet.projet)
