from decimal import Decimal

import pytest
from django.forms import ValidationError

from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.mark.parametrize(
    "montant, assiette, finance_cout_total, expected_taux",
    (
        (1_000, 2_000, 4_000, 50),
        (1_000, 2_000, None, 50),
        (1_000, None, 4_000, 25),
        (1_000, None, None, 0),
    ),
)
@pytest.mark.django_db
def test_progammation_projet_taux(montant, assiette, finance_cout_total, expected_taux):
    dotation_projet = DotationProjetFactory(
        assiette=assiette, projet__dossier_ds__finance_cout_total=finance_cout_total
    )
    programmation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet, montant=montant
    )
    assert isinstance(programmation_projet.taux, Decimal)
    assert programmation_projet.taux == expected_taux


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
    SimulationProjetFactory.create_batch(
        4,
        simulation=simulation,
        dotation_projet__dotation=simulation.enveloppe.dotation,
        status=SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
    )


@pytest.mark.django_db
def test_get_projet_status_summary(simulation, simulation_projects):
    summary = simulation.get_projet_status_summary()

    expected_summary = {
        SimulationProjet.STATUS_REFUSED: 3,
        SimulationProjet.STATUS_PROCESSING: 1,
        SimulationProjet.STATUS_ACCEPTED: 2,
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: 0,
        SimulationProjet.STATUS_PROVISIONALLY_REFUSED: 4,
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
