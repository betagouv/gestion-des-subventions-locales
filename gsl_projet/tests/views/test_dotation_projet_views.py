import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR, PROJET_STATUS_PROCESSING
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def accepted_simulation_projet(collegue, perimetre_departemental):
    detr_enveloppe = DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )
    simulation = SimulationFactory(enveloppe=detr_enveloppe)
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
        projet__dossier_ds__perimetre=collegue.perimetre,
        projet__is_budget_vert=False,
        dotation=DOTATION_DETR,
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
        simulation=simulation,
    )


@pytest.mark.parametrize(
    "value, expected_value", (("True", True), ("False", False), ("", None))
)
def test_patch_detr_avis_commission(
    client_with_user_logged, accepted_simulation_projet, value, expected_value
):
    url = reverse(
        "projet:patch-dotation-projet",
        kwargs={"pk": accepted_simulation_projet.dotation_projet.pk},
    )
    response = client_with_user_logged.post(
        url,
        {"detr_avis_commission": value},
        follow=True,
    )

    assert response.status_code == 200
    accepted_simulation_projet.dotation_projet.refresh_from_db()
    assert (
        accepted_simulation_projet.dotation_projet.detr_avis_commission
        is expected_value
    )
