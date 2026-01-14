"""
Tests for view form selection with double dotation projects.

These tests verify that the ProgrammationStatusUpdateView correctly selects
the appropriate form (RefuseProjetForm, DismissProjetForm, or SimulationProjetStatusForm)
based on the combined status of all dotations.
"""

from unittest import mock

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_save_dossier():
    """Mock save_one_dossier_from_ds for all tests in this module."""
    with mock.patch(
        "gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds"
    ):
        yield


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
def double_dotation_projet(collegue):
    """Create a projet with both DETR and DSIL dotations."""
    projet = ProjetFactory(perimetre=collegue.perimetre)

    # Add the collegue as an instructeur on the dossier
    projet.dossier_ds.ds_instructeurs.add(collegue.ds_profile)

    detr_dotation = DotationProjetFactory(
        projet=projet,
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
    )
    dsil_dotation = DotationProjetFactory(
        projet=projet,
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_PROCESSING,
        assiette=15_000,
    )
    return {
        "projet": projet,
        "detr_dotation": detr_dotation,
        "dsil_dotation": dsil_dotation,
    }


class TestFormSelectionWhenRefusingOneDoubleDotation:
    """Test that the view selects the correct form when refusing one dotation of a double dotation project."""

    def test_uses_simulation_form_when_refusing_detr_with_dsil_processing(
        self, client_with_user_logged, double_dotation_projet
    ):
        """
        When refusing DETR with DSIL still PROCESSING, the view should use SimulationProjetStatusForm
        and show the notify_later_confirmation_modal template.
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        projet = double_dotation_projet["projet"]

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )

        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Verify the correct template is used (double dotation confirmation)
        assert "htmx/notify_later_confirmation_modal.html" in [
            t.name for t in response.templates
        ]

        # Verify context shows new_projet_status is PROCESSING (not REFUSED)
        # because DSIL is still processing
        assert response.context["new_projet_status"] == PROJET_STATUS_PROCESSING
        assert (
            response.context["new_simulation_status"] == SimulationProjet.STATUS_REFUSED
        )

    def test_uses_refuse_form_when_refusing_detr_with_dsil_refused(
        self, client_with_user_logged, double_dotation_projet
    ):
        """
        When refusing DETR with DSIL already REFUSED, the view should use RefuseProjetForm
        and show the notify_project_confirmation_modal template.
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        # Set DSIL to refused
        dsil_dotation.status = PROJET_STATUS_REFUSED
        dsil_dotation.save()

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )

        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Verify the correct template is used (notify project)
        assert "htmx/notify_project_confirmation_modal.html" in [
            t.name for t in response.templates
        ]

        # Verify context shows new_projet_status is REFUSED
        # because all dotations are now refused
        assert response.context["new_projet_status"] == PROJET_STATUS_REFUSED
        assert (
            response.context["new_simulation_status"] == SimulationProjet.STATUS_REFUSED
        )

    def test_uses_simulation_form_when_refusing_detr_with_dsil_accepted(
        self, mock_save_dossier, client_with_user_logged, double_dotation_projet
    ):
        """
        When refusing DETR with DSIL ACCEPTED, the view should use SimulationProjetStatusForm
        and show the notify_later_confirmation_modal template (because projet is optimistically ACCEPTED).
        Project status should be ACCEPTED (optimistic).
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        # Set DSIL to accepted
        dsil_dotation.status = PROJET_STATUS_ACCEPTED
        dsil_dotation.save()

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )

        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Verify the correct template is used (accept confirmation because projet becomes ACCEPTED)
        assert "htmx/notify_later_confirmation_modal.html" in [
            t.name for t in response.templates
        ]

        # Verify context shows new_projet_status is ACCEPTED (optimistic)
        assert response.context["new_projet_status"] == PROJET_STATUS_ACCEPTED
        assert (
            response.context["new_simulation_status"] == SimulationProjet.STATUS_REFUSED
        )


class TestFormSelectionWhenDismissingOneDoubleDotation:
    """Test that the view selects the correct form when dismissing one dotation of a double dotation project."""

    def test_uses_simulation_form_when_dismissing_dsil_with_detr_processing(
        self, client_with_user_logged, double_dotation_projet
    ):
        """
        When dismissing DSIL with DETR still PROCESSING, the view should use SimulationProjetStatusForm
        and show the notify_later_confirmation_modal template.
        """
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        # Create simulation projet for DSIL
        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[dsil_simulation_projet.id, SimulationProjet.STATUS_DISMISSED],
        )

        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Verify the correct template is used (double dotation confirmation)
        assert "htmx/notify_later_confirmation_modal.html" in [
            t.name for t in response.templates
        ]

        # Verify context shows new_projet_status is PROCESSING
        assert response.context["new_projet_status"] == PROJET_STATUS_PROCESSING
        assert (
            response.context["new_simulation_status"]
            == SimulationProjet.STATUS_DISMISSED
        )

    def test_uses_dismiss_form_when_dismissing_dsil_with_detr_dismissed(
        self, mock_save_dossier, client_with_user_logged, double_dotation_projet
    ):
        """
        When dismissing DSIL with DETR already DISMISSED, the view should use DismissProjetForm
        and show the notify_project_confirmation_modal template.
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        # Set DETR to dismissed
        detr_dotation.status = PROJET_STATUS_DISMISSED
        detr_dotation.save()

        # Create simulation projet for DSIL
        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[dsil_simulation_projet.id, SimulationProjet.STATUS_DISMISSED],
        )

        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Verify the correct template is used (notify project)
        assert "htmx/notify_project_confirmation_modal.html" in [
            t.name for t in response.templates
        ]

        # Verify context shows new_projet_status is DISMISSED
        assert response.context["new_projet_status"] == PROJET_STATUS_DISMISSED
        assert (
            response.context["new_simulation_status"]
            == SimulationProjet.STATUS_DISMISSED
        )

    def test_uses_dismiss_form_when_dismissing_dsil_with_detr_refused(
        self, mock_save_dossier, client_with_user_logged, double_dotation_projet
    ):
        """
        When dismissing DSIL with DETR REFUSED, the view should use DismissProjetForm.
        Project status should be DISMISSED (dismissed takes precedence over refused).
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        # Set DETR to refused
        detr_dotation.status = PROJET_STATUS_REFUSED
        detr_dotation.save()

        # Create simulation projet for DSIL
        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[dsil_simulation_projet.id, SimulationProjet.STATUS_DISMISSED],
        )

        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Verify the correct template is used (notify project)
        assert "htmx/notify_project_confirmation_modal.html" in [
            t.name for t in response.templates
        ]

        # Verify context shows new_projet_status is DISMISSED (precedence over refused)
        assert response.context["new_projet_status"] == PROJET_STATUS_DISMISSED
        assert (
            response.context["new_simulation_status"]
            == SimulationProjet.STATUS_DISMISSED
        )


class TestFormSelectionWhenAcceptingOneDoubleDotation:
    """Test that the view selects the correct form when accepting one dotation of a double dotation project."""

    def test_uses_simulation_form_when_accepting_detr_with_dsil_processing(
        self, mock_save_dossier, client_with_user_logged, double_dotation_projet
    ):
        """
        When accepting DETR with DSIL still PROCESSING, the view should use SimulationProjetStatusForm
        and show the notify_later_confirmation_modal template.
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        projet = double_dotation_projet["projet"]

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_ACCEPTED],
        )

        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        assert response.status_code == 200

        # Verify the correct template is used (double_dotation_confirmation)
        assert "htmx/notify_later_confirmation_modal.html" in [
            t.name for t in response.templates
        ]


class TestFormPostSubmission:
    """Test that form submission correctly triggers the right behavior."""

    @mock.patch("gsl_demarches_simplifiees.importer.dossier.save_one_dossier_from_ds")
    @mock.patch("gsl_simulation.forms.DsMutator.dossier_refuser")
    def test_post_refuse_with_both_refused_calls_ds(
        self,
        mock_ds_refuser,
        mock_save_dossier,
        client_with_user_logged,
        double_dotation_projet,
    ):
        """
        When POSTing to refuse DETR with DSIL already refused,
        the view should call DN refuser because all dotations are refused.
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        # Set DSIL to refused
        dsil_dotation.status = PROJET_STATUS_REFUSED
        dsil_dotation.save()

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )

        data = {"justification": "Budget insuffisant"}
        response = client_with_user_logged.post(
            url, data, headers={"HX-Request": "true"}
        )

        # Verify DN was called
        mock_ds_refuser.assert_called_once()

        # Verify we get a success response
        assert response.status_code == 200

    def test_post_refuse_with_dsil_processing_no_ds_call(
        self, mock_save_dossier, client_with_user_logged, double_dotation_projet
    ):
        """
        When POSTing to refuse DETR with DSIL still processing,
        the view should NOT call DN because DSIL is not in a final state.
        """
        detr_dotation = double_dotation_projet["detr_dotation"]
        projet = double_dotation_projet["projet"]

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )

        # POST with empty data (SimulationProjetStatusForm doesn't require justification)
        response = client_with_user_logged.post(url, {}, headers={"HX-Request": "true"})

        # Verify we get a success response
        assert response.status_code == 200

        # Verify projet is NOT notified
        projet.refresh_from_db()
        assert projet.notified_at is None
