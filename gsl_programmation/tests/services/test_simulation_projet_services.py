import pytest

from gsl_programmation.models import Simulation
from gsl_programmation.services import ProjetService
from gsl_programmation.tests.factories import SimulationFactory, SimulationProjetFactory
from gsl_projet.models import Projet
from gsl_projet.tests.factories import ProjetFactory

### ProjetService


@pytest.fixture
def simulation() -> Simulation:
    return SimulationFactory()


@pytest.fixture
def projets_with_assiette(simulation) -> list[Projet]:
    for amount in (10_000, 20_000, 30_000):
        p = ProjetFactory(assiette=amount)
        SimulationProjetFactory(projet=p, simulation=simulation)


@pytest.fixture
def projets_without_assiette_but_finance_cout_total_from_dossier_ds(
    simulation,
) -> list[Projet]:
    for amount in (15_000, 25_000):
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
    qs = Projet.objects.all()
    assert ProjetService.get_total_cost(qs) == 60_000


@pytest.mark.django_db
def test_get_total_cost_without_assiette(
    simulation, projets_without_assiette_but_finance_cout_total_from_dossier_ds
):
    qs = Projet.objects.all()

    assert ProjetService.get_total_cost(qs) == 40_000


@pytest.mark.django_db
def test_get_total_cost(
    simulation,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
):
    qs = Projet.objects.all()
    assert ProjetService.get_total_cost(qs) == 100_000


@pytest.mark.django_db
def test_get_same_total_cost_even_if_there_is_other_projets(
    simulation,
    projets_with_assiette,
    projets_without_assiette_but_finance_cout_total_from_dossier_ds,
    projets_with_assiette_but_not_in_simulation,
):
    qs = Projet.objects.filter(simulationprojet__simulation=simulation).all()
    assert ProjetService.get_total_cost(qs) == 100_000


@pytest.mark.django_db
def test_get_total_amount_granted(simulation):
    SimulationProjetFactory(simulation=simulation, montant=1000)
    SimulationProjetFactory(simulation=simulation, montant=2000)
    SimulationProjetFactory(montant=4000)

    qs = Projet.objects.filter(simulationprojet__simulation=simulation).all()
    assert ProjetService.get_total_amount_granted(qs) == 3000


@pytest.fixture
def projets_with_dossier_ds__demande_montant_not_in_simulation() -> list[Projet]:
    for amount in (10_000, 2_000):
        p = ProjetFactory(
            dossier_ds__demande_montant=amount,
        )
        SimulationProjetFactory(projet=p)


@pytest.fixture
def projets_with_dossier_ds__demande_montant_in_simulation(
    simulation,
) -> list[Projet]:
    for amount in (15_000, 25_000):
        p = ProjetFactory(
            dossier_ds__demande_montant=amount,
        )

        SimulationProjetFactory(projet=p, simulation=simulation)


@pytest.mark.django_db
def test_get_total_amount_asked(
    simulation,
    projets_with_dossier_ds__demande_montant_in_simulation,
    projets_with_dossier_ds__demande_montant_not_in_simulation,
):
    qs = Projet.objects.filter(simulationprojet__simulation=simulation).all()
    assert ProjetService.get_total_amount_asked(qs) == 15_000 + 25_000
