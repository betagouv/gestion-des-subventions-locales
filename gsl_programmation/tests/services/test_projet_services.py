import pytest

from gsl_programmation.models import SimulationProjet
from gsl_programmation.services import SimulationProjetService
from gsl_programmation.tests.factories import SimulationProjetFactory
from gsl_projet.tests.factories import ProjetFactory


@pytest.fixture
def projet():
    return ProjetFactory(assiette=1000)


@pytest.mark.django_db
def test_update_status():
    simulation_projet = SimulationProjetFactory(status=SimulationProjet.STATUS_DRAFT)
    new_status = SimulationProjet.STATUS_VALID

    SimulationProjetService.update_status(simulation_projet, new_status)

    assert simulation_projet.status == new_status


@pytest.mark.django_db
def test_update_taux(projet):
    simulation_projet = SimulationProjetFactory(projet=projet, taux=10.0)
    new_taux = 15.0

    SimulationProjetService.update_taux(simulation_projet, new_taux)

    assert simulation_projet.taux == new_taux
    assert simulation_projet.montant == 150.0


@pytest.mark.django_db
def test_update_montant(projet):
    simulation_projet = SimulationProjetFactory(projet=projet, montant=1000.0)
    new_montant = 500.0

    SimulationProjetService.update_montant(simulation_projet, new_montant)

    assert simulation_projet.montant == new_montant
    assert simulation_projet.taux == 50.0
