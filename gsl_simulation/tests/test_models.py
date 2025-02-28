import pytest
from django.forms import ValidationError

from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.fixture
def simulation() -> Simulation:
    return SimulationFactory()


@pytest.fixture
def simulation_projects(simulation):
    SimulationProjetFactory.create_batch(
        2,
        simulation=simulation,
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory(
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory.create_batch(
        3,
        simulation=simulation,
        status=SimulationProjet.STATUS_REFUSED,
    )
    SimulationProjetFactory.create_batch(
        1,
        simulation=simulation,
        status=SimulationProjet.STATUS_PROCESSING,
    )


@pytest.mark.django_db
def test_get_projet_status_summary(simulation, simulation_projects):
    summary = simulation.get_projet_status_summary()

    expected_summary = {
        SimulationProjet.STATUS_REFUSED: 3,
        SimulationProjet.STATUS_PROCESSING: 1,
        SimulationProjet.STATUS_ACCEPTED: 2,
        SimulationProjet.STATUS_PROVISOIRE: 0,
        "notified": 0,
    }

    assert summary == expected_summary


def test_simulation_projet_cant_have_a_montant_higher_than_projet_assiette():
    projet = ProjetFactory.build(assiette=100, dossier_ds__finance_cout_total=200)
    with pytest.raises(ValidationError) as exc_info:
        pp = SimulationProjetFactory.build(projet=projet, montant=101)
        pp.full_clean()
    assert (
        "Le montant de la simulation ne peut pas être supérieur à l'assiette du projet."
        in str(exc_info.value.message_dict.get("montant")[0])
    )


def test_simulation_projet_cant_have_a_montant_higher_than_projet_cout_total():
    projet = ProjetFactory.build(dossier_ds__finance_cout_total=100)
    with pytest.raises(ValidationError) as exc_info:
        pp = SimulationProjetFactory.build(projet=projet, montant=101)
        pp.full_clean()
    assert (
        "Le montant de la simulation ne peut pas être supérieur au coût total du projet."
        in str(exc_info.value.message_dict.get("montant")[0])
    )


def test_simulation_projet_cant_have_a_taux_higher_than_100():
    with pytest.raises(ValidationError) as exc_info:
        pp = SimulationProjetFactory.build(taux=101)
        pp.full_clean()
    assert "Le taux de la simulation ne peut pas être supérieur à 100" in str(
        exc_info.value.message_dict.get("taux")[0]
    )
