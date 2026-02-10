from datetime import date
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
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
def dsil_enveloppe(perimetre_departemental):
    return DsilEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )


@pytest.fixture
def detr_simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def dsil_simulation(dsil_enveloppe):
    return SimulationFactory(enveloppe=dsil_enveloppe)


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def notified_simulation_projet(collegue, detr_simulation):
    """A simulation projet with a notified projet."""
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_ACCEPTED,
        projet__dossier_ds__perimetre=collegue.perimetre,
        projet__notified_at=timezone.now(),
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        notified_at=date.today(),
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=5000,
        simulation=detr_simulation,
    )


@pytest.fixture
def non_notified_simulation_projet(collegue, detr_simulation):
    """A simulation projet with a non-notified projet."""
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=collegue.perimetre,
        projet__notified_at=None,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=5000,
        simulation=detr_simulation,
    )


@pytest.fixture
def double_dotation_projet(collegue, detr_simulation, dsil_simulation):
    """A projet with both DETR and DSIL dotations."""
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=timezone.now(),
    )

    detr_dotation = DotationProjetFactory(
        projet=projet,
        status=PROJET_STATUS_ACCEPTED,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )

    dsil_dotation = DotationProjetFactory(
        projet=projet,
        status=PROJET_STATUS_ACCEPTED,
        dotation=DOTATION_DSIL,
        assiette=15_000,
    )

    ProgrammationProjetFactory(
        dotation_projet=detr_dotation,
        notified_at=date.today(),
    )

    ProgrammationProjetFactory(
        dotation_projet=dsil_dotation,
        notified_at=date.today(),
    )

    detr_simulation_projet = SimulationProjetFactory(
        dotation_projet=detr_dotation,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=5000,
        simulation=detr_simulation,
    )

    SimulationProjetFactory(
        dotation_projet=dsil_dotation,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=7000,
        simulation=dsil_simulation,
    )

    return detr_simulation_projet


class TestRevertNotifiedProjetToProcessingView:
    def test_button_not_displayed_for_non_notified_projects(
        self, client_with_user_logged, non_notified_simulation_projet
    ):
        """The revert button should not be displayed for non-notified projects."""
        url = reverse(
            "simulation:simulation-projet-detail",
            args=[non_notified_simulation_projet.id],
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        assert "Repasser en traitement" not in response.content.decode()

    def test_button_displayed_for_notified_projects(
        self, client_with_user_logged, notified_simulation_projet
    ):
        """The revert button should be displayed for notified projects."""
        url = reverse(
            "simulation:simulation-projet-detail", args=[notified_simulation_projet.id]
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        assert "Repasser en traitement" in response.content.decode()

    def test_get_modal_returns_single_dotation_template(
        self, client_with_user_logged, notified_simulation_projet
    ):
        """GET request should return the single dotation modal template."""
        url = reverse(
            "simulation:simulation-projet-update-simulation-status",
            args=[notified_simulation_projet.id, SimulationProjet.STATUS_PROCESSING],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200
        assert (
            "Revenir au statut «&nbsp;en traitement&nbsp;»" in response.content.decode()
        )

    def test_get_modal_returns_double_dotation_template(
        self, client_with_user_logged, double_dotation_projet
    ):
        """GET request for double dotation projet should return the double dotation modal template."""
        url = reverse(
            "simulation:simulation-projet-update-simulation-status",
            args=[double_dotation_projet.id, SimulationProjet.STATUS_PROCESSING],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200
        assert "Remettre la demande de financement DETR" in response.content.decode()

    @patch("gsl_projet.models.DsService.update_ds_annotations_for_one_dotation")
    @patch("gsl_projet.models.DsService.repasser_en_instruction")
    def test_post_reverts_projet_to_processing(
        self,
        mock_repasser_en_instruction,
        mock_update_annotations,
        client_with_user_logged,
        notified_simulation_projet,
    ):
        """POST request should revert the projet to processing status."""
        url = reverse(
            "simulation:simulation-projet-update-simulation-status",
            args=[notified_simulation_projet.id, SimulationProjet.STATUS_PROCESSING],
        )

        response = client_with_user_logged.post(url, {}, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Refresh from DB
        notified_simulation_projet.refresh_from_db()

        # Check that the status was reverted
        assert notified_simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert (
            notified_simulation_projet.dotation_projet.status
            == PROJET_STATUS_PROCESSING
        )

        # Check success message
        messages = list(get_messages(response.wsgi_request))
        assert len(messages) == 1
        assert messages[0].level == 20  # INFO
        assert "bien repassée en traitement" in messages[0].message

        # Check that DS was updated
        mock_repasser_en_instruction.assert_called_once()
        mock_update_annotations.assert_called_once()

    @patch("gsl_projet.models.DsService.update_ds_annotations_for_one_dotation")
    @patch("gsl_simulation.forms.DsService.repasser_en_instruction")
    def test_post_clears_notified_at(
        self,
        mock_repasser_en_instruction,
        mock_update_annotations,
        client_with_user_logged,
        notified_simulation_projet,
    ):
        """POST request should clear the notified_at field."""
        assert notified_simulation_projet.projet.notified_at is not None

        url = reverse(
            "simulation:simulation-projet-update-simulation-status",
            args=[notified_simulation_projet.id, SimulationProjet.STATUS_PROCESSING],
        )

        client_with_user_logged.post(url, {}, headers={"HX-Request": "true"})

        # Refresh from DB
        notified_simulation_projet.refresh_from_db()

        # Check that notified_at was cleared
        assert notified_simulation_projet.projet.notified_at is None

    @patch("gsl_projet.models.DsService.update_ds_annotations_for_one_dotation")
    @patch("gsl_simulation.forms.DsService.repasser_en_instruction")
    def test_post_deletes_programmation_projet(
        self,
        mock_repasser_en_instruction,
        mock_update_annotations,
        client_with_user_logged,
        notified_simulation_projet,
    ):
        """POST request should delete the associated ProgrammationProjet."""
        # Verify that ProgrammationProjet exists
        assert hasattr(
            notified_simulation_projet.dotation_projet, "programmation_projet"
        )

        url = reverse(
            "simulation:simulation-projet-update-simulation-status",
            args=[notified_simulation_projet.id, SimulationProjet.STATUS_PROCESSING],
        )

        client_with_user_logged.post(url, {}, headers={"HX-Request": "true"})

        # Refresh from DB
        notified_simulation_projet.dotation_projet.refresh_from_db()

        # Check that ProgrammationProjet was deleted
        assert not hasattr(
            notified_simulation_projet.dotation_projet, "programmation_projet"
        )
