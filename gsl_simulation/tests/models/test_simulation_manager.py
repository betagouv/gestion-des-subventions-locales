import pytest

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.tests.factories import (
    DsilEnveloppeFactory,
)
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.models import Projet
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.mark.django_db
def test_slug_model_creation_and_slug_generation():
    perimetre_regional = PerimetreRegionalFactory()
    user = CollegueFactory(perimetre=perimetre_regional)
    enveloppe_dsil = DsilEnveloppeFactory(perimetre=perimetre_regional)

    Simulation.objects.create(created_by=user, title="Test", enveloppe=enveloppe_dsil)

    simulation = Simulation.objects.get(enveloppe=enveloppe_dsil)
    assert simulation.slug == "test"


@pytest.fixture
def simulation():
    return SimulationFactory()


@pytest.mark.django_db
def test_get_total_amount_granted(simulation):
    # must be included
    accepted_projet = SimulationProjetFactory(
        simulation=simulation,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_200,
        dotation_projet__dotation=DOTATION_DETR,
    )
    provisionally_accepted_projet = SimulationProjetFactory(
        simulation=simulation,
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        montant=2_300,
        dotation_projet__dotation=DOTATION_DETR,
    )

    # must not be included
    ## other statuses
    SimulationProjetFactory(
        simulation=simulation,
        status=SimulationProjet.STATUS_REFUSED,
        montant=3_000,
        dotation_projet__dotation=DOTATION_DETR,
    )
    SimulationProjetFactory(
        simulation=simulation,
        status=SimulationProjet.STATUS_DISMISSED,
        montant=4_000,
        dotation_projet__dotation=DOTATION_DETR,
    )
    SimulationProjetFactory(
        simulation=simulation,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=5_000,
        dotation_projet__dotation=DOTATION_DETR,
    )
    ## not in simulation
    SimulationProjetFactory(
        dotation_projet=accepted_projet.dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=6_000,
    )
    SimulationProjetFactory(
        dotation_projet=provisionally_accepted_projet.dotation_projet,
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        montant=8_000,
    )

    qs = Projet.objects.filter(dotationprojet__simulationprojet__simulation=simulation)
    assert simulation.get_total_amount_granted(qs) == 1_200 + 2_300


@pytest.mark.django_db
def test_get_total_amount_granted_with_empty_qs(simulation):
    qs = Projet.objects.all()
    assert simulation.get_total_amount_granted(qs) == 0
