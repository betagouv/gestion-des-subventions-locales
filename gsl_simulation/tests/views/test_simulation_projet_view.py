import pytest

from gsl_simulation.tests.factories import SimulationProjetFactory
from gsl_simulation.views.simulation_projet_views import (
    _get_other_dotation_simulation_projet,
)


@pytest.mark.django_db
def test_get_other_dotation_simulation_projet():
    # Without any other simulation projet with an other dotation
    original_simulation_projet = SimulationProjetFactory(
        simulation__enveloppe__dotation="DSIL"
    )
    _other_simulation_projet_with_same_dotation = SimulationProjetFactory(
        dotation_projet=original_simulation_projet.dotation_projet
    )
    assert _get_other_dotation_simulation_projet(original_simulation_projet) is None

    # With two simulation projets with an other dotation. We should get the last updated
    simulation_projet_with_other_dotation = SimulationProjetFactory(
        dotation_projet__dotation="DETR",
        dotation_projet__projet=original_simulation_projet.projet,
    )
    second_simulation_projet_with_other_dotation = SimulationProjetFactory(
        dotation_projet__dotation="DETR",
        dotation_projet__projet=original_simulation_projet.projet,
    )

    assert (
        _get_other_dotation_simulation_projet(original_simulation_projet)
        == second_simulation_projet_with_other_dotation
    )

    # We check that we get the last updated simulation projet with an other dotation
    simulation_projet_with_other_dotation.montant = 1000
    simulation_projet_with_other_dotation.save()
    assert (
        _get_other_dotation_simulation_projet(original_simulation_projet)
        == simulation_projet_with_other_dotation
    )
