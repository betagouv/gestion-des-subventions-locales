import pytest
from django.conf import settings
from django.db import IntegrityError

from gsl_projet.constants import DOTATION_DETR
from gsl_projet.tests.factories import (
    DetrProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

skip_on_sqlite = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="nulls_distinct constraints are not enforced on SQLite",
)


@pytest.fixture
def simulation():
    return SimulationFactory()


@skip_on_sqlite
@pytest.mark.django_db
def test_projet_only_once_per_simulation_and_enveloppe(simulation):
    dotation_projet = DetrProjetFactory()
    simulation_projet_un = SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=dotation_projet,
    )
    with pytest.raises(IntegrityError):
        sp = SimulationProjet(
            simulation=simulation_projet_un.simulation,
            dotation_projet=dotation_projet,
            montant=0,
        )
        sp.save()


@pytest.mark.django_db
def test_projet_twice_per_simulation_with_different_projet(simulation):
    SimulationProjetFactory(
        simulation=simulation,
        dotation_projet=DetrProjetFactory(),
    )
    SimulationProjetFactory(
        simulation=simulation, dotation_projet__dotation=DOTATION_DETR
    )


@pytest.mark.django_db
def test_projet_twice_per_simulation_with_different_simulation():
    simulation_projet = SimulationProjetFactory(
        dotation_projet=DetrProjetFactory(),
    )
    SimulationProjetFactory(dotation_projet=simulation_projet.dotation_projet)
