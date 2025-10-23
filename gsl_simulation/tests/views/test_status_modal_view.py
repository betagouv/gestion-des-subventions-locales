from datetime import date
from unittest import mock
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR, PROJET_STATUS_PROCESSING
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

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
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def simulation_projet(collegue, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    # Create a SimulationProjet within the user's perimeter. Let the factory handle creating a matching Simulation
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=1000,
        simulation=simulation,
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


@mock.patch("gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds")
def test_refuse_modal_allows_non_notified_projects(
    mock_save_dossier, client_with_user_logged, simulation_projet
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

    assert response.status_code == 200


@mock.patch("gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds")
@mock.patch("gsl_demarches_simplifiees.services.DsService.dismiss_in_ds")
def test_dismiss_projet(
    mock_dismiss_in_ds,
    mock_save_one_dossier_from_ds,
    client_with_user_logged,
    simulation_projet,
):
    data = {"justification": "Ma motivation"}

    url = reverse("gsl_simulation:dismiss-form", args=[simulation_projet.id])
    response = client_with_user_logged.post(url, data, headers={"HX-Request": "true"})

    assert response.status_code == 200

    mock_save_one_dossier_from_ds.assert_called_once_with(
        simulation_projet.projet.dossier_ds
    )

    mock_dismiss_in_ds.assert_called_once_with(
        simulation_projet.projet.dossier_ds,
        client_with_user_logged.user,
        motivation="Ma motivation",
    )

    messages = get_messages(response.wsgi_request)
    assert len(messages) == 1

    message = list(messages)[0]
    assert message.level == 25
    assert (
        message.message
        == "Le projet a bien été classé sans suite sur Démarches Simplifiées."
    )
    assert message.extra_tags == "dismissed"
