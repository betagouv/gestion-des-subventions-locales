import pytest
from django.db import IntegrityError

from gsl_projet.tests.factories import (
    DetrProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def simulation():
    return SimulationFactory()


@pytest.mark.django_db
def test_projet_only_once_per_simulation_and_enveloppe(simulation):
    dotation_projet = DetrProjetFactory()
    simulation_projet_un = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet,
    )
    with pytest.raises(IntegrityError) as exc_info:
        sp = SimulationProjet(
            simulation=simulation_projet_un.simulation,
            dotation_projet=dotation_projet,
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
        dotation_projet=DetrProjetFactory(),
    )
    SimulationProjetFactory(simulation=simulation)


@pytest.mark.django_db
def test_projet_twice_per_simulation_with_different_simulation():
    simulation_projet = SimulationProjetFactory(
        dotation_projet=DetrProjetFactory(),
    )
    SimulationProjetFactory(dotation_projet=simulation_projet.dotation_projet)
