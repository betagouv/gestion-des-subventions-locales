import pytest

from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory
from gsl_simulation.views.simulation_projet_views import (
    _get_other_dotation_simulation_projet,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def projet():
    return ProjetFactory()


@pytest.fixture
def detr_projet(projet):
    return DotationProjetFactory(projet=projet, dotation="DETR")


@pytest.fixture
def dsil_projet(projet):
    return DotationProjetFactory(projet=projet, dotation="DSIL")


@pytest.fixture
def dsil_simulation_projets(dsil_projet):
    return [
        SimulationProjetFactory(
            dotation_projet=dsil_projet,
        )
        for _ in range(3)
    ]


@pytest.fixture
def detr_simulation_projets(detr_projet):
    return [
        SimulationProjetFactory(
            dotation_projet=detr_projet,
        )
        for _ in range(3)
    ]


def test_get_other_dotation_simulation_projet_without_other_dotation_simulation_projets(
    dsil_simulation_projets,
):
    simulation_projet = dsil_simulation_projets[0]

    result = _get_other_dotation_simulation_projet(simulation_projet)

    assert result is None


def test_get_other_dotation_simulation_projet_with_other_dotation_simulation_projets(
    dsil_simulation_projets, detr_simulation_projets
):
    simulation_projet = dsil_simulation_projets[0]

    result = _get_other_dotation_simulation_projet(simulation_projet)

    expected_simulation_projet = (
        SimulationProjet.objects.filter(
            dotation_projet__projet=simulation_projet.dotation_projet.projet,
            dotation_projet__dotation="DETR",
        )
        .order_by("-updated_at")
        .first()
    )

    assert result == expected_simulation_projet


def test_get_other_dotation_simulation_projet_give_the_last_updated(
    dsil_simulation_projets, detr_simulation_projets
):
    detr_simu_to_update = detr_simulation_projets[1]
    detr_simu_to_update.montant = 1000
    detr_simu_to_update.save()
    simulation_projet = dsil_simulation_projets[0]

    result = _get_other_dotation_simulation_projet(simulation_projet)

    assert result == detr_simu_to_update
