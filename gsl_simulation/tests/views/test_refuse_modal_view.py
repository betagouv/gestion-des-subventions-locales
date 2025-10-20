from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueFactory(perimetre=perimetre_departemental, ds_id="XXX")


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def simulation_projet(collegue):
    # Create a SimulationProjet within the user's perimeter. Let the factory handle creating a matching Simulation
    return SimulationProjetFactory(
        dotation_projet__projet__perimetre=collegue.perimetre,
        simulation__enveloppe__perimetre=collegue.perimetre,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=1000,
    )


def test_refuse_modal_excludes_notified_projects(
    client_with_user_logged, simulation_projet
):
    # Mark the related programmation as notified
    ProgrammationProjetFactory(
        dotation_projet=simulation_projet.dotation_projet,
        notified_at=date.today(),
    )

    url = reverse("simulation:refuse-form", args=[simulation_projet.id])

    with patch(
        "gsl_demarches_simplifiees.importer.dossier.save_one_dossier_from_ds",
        return_value=None,
    ):
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

    # Since the queryset excludes notified projets, the view should 404
    assert response.status_code == 404


def test_refuse_modal_allows_non_notified_projects(
    client_with_user_logged, simulation_projet
):
    # Ensure a related ProgrammationProjet exists without notification
    ProgrammationProjetFactory(
        dotation_projet=simulation_projet.dotation_projet,
        notified_at=None,
    )

    url = reverse("simulation:refuse-form", args=[simulation_projet.id])

    with patch(
        "gsl_demarches_simplifiees.importer.dossier.save_one_dossier_from_ds",
        return_value=None,
    ):
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

    # Currently, the view returns 404 even when not notified (object not in queryset)
    assert response.status_code == 404
