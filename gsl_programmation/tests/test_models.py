import pytest

from gsl_programmation.models import Simulation
from gsl_programmation.tests.factories import SimulationFactory, SimulationProjetFactory
from gsl_projet.models import Projet
from gsl_projet.tests.factories import ProjetFactory


@pytest.fixture
def simulation() -> Simulation:
    return SimulationFactory()


@pytest.fixture
def projets_with_assiette(simulation) -> list[Projet]:
    for amount in [10_000, 20_000, 30_000]:
        p = ProjetFactory(assiette=amount)
        SimulationProjetFactory(projet=p, simulation=simulation)


@pytest.fixture
def projets_without_assiette_but_finance_cout_total_from_dossier_ds(
    simulation,
) -> list[Projet]:
    for amount in [15_000, 25_000]:
        p = ProjetFactory(
            dossier_ds__finance_cout_total=amount,
            assiette=None,
        )

        SimulationProjetFactory(projet=p, simulation=simulation)


@pytest.fixture
def projets_with_assiette_but_not_in_simulation() -> list[Projet]:
    p = ProjetFactory(assiette=50_000)
    SimulationProjetFactory(projet=p)


@pytest.mark.django_db
def test_get_total_cost_with_assiette(simulation, projets_with_assiette):
    assert simulation.get_total_cost() == 60_000


@pytest.mark.django_db
def test_get_total_cost_without_assiette(
    simulation, projets_without_assiette_but_finance_cout_total_from_dossier_ds
):
    assert simulation.get_total_cost() == 40_000


@pytest.mark.django_db
def test_get_total_cost(
    simulation,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
):
    assert simulation.get_total_cost() == 100_000


@pytest.mark.django_db
def test_get_same_total_cost_even_if_there_is_other_projets(
    simulation,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
    projets_with_assiette_but_not_in_simulation,
):
    assert simulation.get_total_cost() == 100_000


@pytest.mark.django_db
def test_get_total_amount_granted(simulation):
    SimulationProjetFactory(simulation=simulation, montant=1000)
    SimulationProjetFactory(simulation=simulation, montant=2000)
    SimulationProjetFactory(montant=4000)
    assert simulation.get_total_amount_granted() == 3000
