import pytest
from django.db import IntegrityError

from gsl_projet.constants import DOTATION_DETR
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def simulation():
    return SimulationFactory()


@pytest.mark.django_db
def test_projet_only_once_per_simulation_and_enveloppe(simulation):
    dotation_projet = DotationProjetFactory(dotation=DOTATION_DETR)
    simulation_projet_un = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet,
    )
    with pytest.raises(IntegrityError) as exc_info:
        sp = SimulationProjet(
            simulation=simulation_projet_un.simulation,
            dotation_projet=dotation_projet,
            projet=dotation_projet.projet,
            montant=0,
            taux=0,
        )
        sp.save()

    assert (
        'duplicate key value violates unique constraint "unique_projet_simulation"'
        in exc_info.value.args[0]
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
