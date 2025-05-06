import pytest
from django.forms import ValidationError

from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import DotationProjetFactory
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
        dotation_projet__dotation=simulation.enveloppe.dotation,
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory(
        status=SimulationProjet.STATUS_ACCEPTED,
        dotation_projet__dotation=simulation.enveloppe.dotation,
    )
    SimulationProjetFactory.create_batch(
        3,
        simulation=simulation,
        dotation_projet__dotation=simulation.enveloppe.dotation,
        status=SimulationProjet.STATUS_REFUSED,
    )
    SimulationProjetFactory.create_batch(
        1,
        simulation=simulation,
        dotation_projet__dotation=simulation.enveloppe.dotation,
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


@pytest.mark.django_db
def test_simulation_projet_cant_have_a_montant_higher_than_projet_assiette():
    dotation_projet = DotationProjetFactory(
        assiette=100, projet__dossier_ds__finance_cout_total=200
    )
    with pytest.raises(ValidationError) as exc_info:
        sp = SimulationProjetFactory(dotation_projet=dotation_projet, montant=101)
        assert sp.montant == 101
        sp.save()
    assert (
        "Le montant de la simulation ne peut pas être supérieur à l'assiette du projet"
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_simulation_projet_cant_have_a_montant_higher_than_projet_cout_total():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        assiette=None,
        projet__dossier_ds__finance_cout_total=100,
    )
    with pytest.raises(ValidationError) as exc_info:
        sp = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            montant=101,
        )
        sp.save()
    assert (
        "Le montant de la simulation ne peut pas être supérieur au coût total du projet"
        in exc_info.value.message_dict.get("montant")[0]
    )


@pytest.mark.django_db
def test_simulation_projet_cant_have_a_taux_higher_than_100():
    with pytest.raises(ValidationError) as exc_info:
        sp = SimulationProjetFactory(taux=101)
        sp.save()
    assert (
        "Le taux de la simulation ne peut pas être supérieur à 100"
        in exc_info.value.message_dict.get("taux")[0]
    )


@pytest.mark.django_db
def test_simulation_projet_must_have_a_dotation_consistency():
    dotation_projet = DotationProjetFactory(dotation=DOTATION_DSIL)
    simulation = SimulationFactory(enveloppe__dotation=DOTATION_DETR)

    with pytest.raises(ValidationError) as exc_info:
        sp = SimulationProjetFactory(
            simulation=simulation,
            dotation_projet=dotation_projet,
        )
        sp.save()
    assert (
        "La dotation du projet doit être la même que la dotation de la simulation."
        in exc_info.value.message_dict.get("dotation_projet")[0]
    )
