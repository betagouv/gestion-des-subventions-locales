"""
Tests for notification tab display logic in simulation projet detail page.

According to requirements:
- Never show from regular projet list tab
- Simple dotation: Show if project is accepted (notified or not)
- Double dotation: Show if at least one dotation_projet is accepted (regardless of notification status)
"""

import pytest
from django.urls import reverse

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
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
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


class TestNotificationTabDisplaySimpleDotation:
    """Test notification tab display for simple (single) dotation projects."""

    def test_notification_tab_shown_when_accepted(
        self, client_with_user_logged, collegue
    ):
        """Notification tab should be shown for accepted projects (simple dotation)."""
        # Create accepted DETR projet
        dotation_projet = DotationProjetFactory(
            projet__perimetre=collegue.perimetre,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
        )
        programmation_projet = ProgrammationProjetFactory(
            dotation_projet=dotation_projet, status="accepted"
        )

        # Create simulation projet
        detr_enveloppe = DetrEnveloppeFactory(perimetre=collegue.perimetre)
        simulation = SimulationFactory(enveloppe=detr_enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet, simulation=simulation
        )

        # Get simulation projet detail page
        url = reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.id}
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        # Check notification tab link is present
        notification_url = reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": programmation_projet.projet.id},
        )
        assert notification_url in response.content.decode()
        assert "Notifications du demandeur" in response.content.decode()

    def test_notification_tab_not_shown_when_processing(
        self, client_with_user_logged, collegue
    ):
        """Notification tab should NOT be shown for processing projects (simple dotation)."""
        # Create processing DETR projet
        dotation_projet = DotationProjetFactory(
            projet__perimetre=collegue.perimetre,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_PROCESSING,
        )

        # Create simulation projet
        detr_enveloppe = DetrEnveloppeFactory(perimetre=collegue.perimetre)
        simulation = SimulationFactory(enveloppe=detr_enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet, simulation=simulation
        )

        # Get simulation projet detail page
        url = reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.id}
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        # Check notification tab link is NOT present
        assert "Notifications du demandeur" not in response.content.decode()


class TestNotificationTabDisplayDoubleDotation:
    """Test notification tab display for double dotation projects."""

    def test_notification_tab_shown_when_detr_accepted_dsil_processing(
        self, client_with_user_logged, collegue
    ):
        """Notification tab shown when DETR is accepted but DSIL is still processing."""
        # Create projet with both dotations
        projet = ProjetFactory(perimetre=collegue.perimetre)

        # DETR accepted
        detr_dotation = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
        )
        detr_programmation = ProgrammationProjetFactory(
            dotation_projet=detr_dotation, status="accepted"
        )

        # DSIL processing
        DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_PROCESSING
        )

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=collegue.perimetre)
        simulation = SimulationFactory(enveloppe=detr_enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation, simulation=simulation
        )

        # Get simulation projet detail page
        url = reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.id}
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        # Check notification tab link IS present (at least one is accepted)
        notification_url = reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": detr_programmation.projet.id},
        )
        assert notification_url in response.content.decode()
        assert "Notifications du demandeur" in response.content.decode()

    def test_notification_tab_shown_when_dsil_accepted_detr_refused(
        self, client_with_user_logged, collegue
    ):
        """Notification tab shown when DSIL is accepted but DETR is refused."""
        # Create projet with both dotations
        projet = ProjetFactory(perimetre=collegue.perimetre)

        # DETR refused
        DotationProjetFactory(
            projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_REFUSED
        )

        # DSIL accepted
        dsil_dotation = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
        )
        dsil_programmation = ProgrammationProjetFactory(
            dotation_projet=dsil_dotation, status="accepted"
        )

        # Create simulation projet for DSIL
        dsil_enveloppe = DsilEnveloppeFactory(perimetre=collegue.perimetre)
        simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation, simulation=simulation
        )

        # Get simulation projet detail page
        url = reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.id}
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        # Check notification tab link IS present (at least one is accepted)
        notification_url = reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": dsil_programmation.projet.id},
        )
        assert notification_url in response.content.decode()
        assert "Notifications du demandeur" in response.content.decode()

    def test_notification_tab_shown_when_both_accepted(
        self, client_with_user_logged, collegue
    ):
        """Notification tab shown when both DETR and DSIL are accepted."""
        # Create projet with both dotations
        projet = ProjetFactory(perimetre=collegue.perimetre)

        # Both accepted
        detr_dotation = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
        )
        detr_programmation = ProgrammationProjetFactory(
            dotation_projet=detr_dotation, status="accepted"
        )

        dsil_dotation = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
        )
        ProgrammationProjetFactory(dotation_projet=dsil_dotation, status="accepted")

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=collegue.perimetre)
        simulation = SimulationFactory(enveloppe=detr_enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation, simulation=simulation
        )

        # Get simulation projet detail page
        url = reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.id}
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        # Check notification tab link IS present (links to first accepted one)
        notification_url = reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": detr_programmation.projet.id},
        )
        assert notification_url in response.content.decode()
        assert "Notifications du demandeur" in response.content.decode()

    def test_notification_tab_not_shown_when_both_processing(
        self, client_with_user_logged, collegue
    ):
        """Notification tab NOT shown when both DETR and DSIL are still processing."""
        # Create projet with both dotations
        projet = ProjetFactory(perimetre=collegue.perimetre)

        # Both processing
        detr_dotation = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
        )

        DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_PROCESSING
        )

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=collegue.perimetre)
        simulation = SimulationFactory(enveloppe=detr_enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation, simulation=simulation
        )

        # Get simulation projet detail page
        url = reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.id}
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        # Check notification tab link is NOT present (none are accepted)
        assert "Notifications du demandeur" not in response.content.decode()

    def test_notification_tab_not_shown_when_both_refused(
        self, client_with_user_logged, collegue
    ):
        """Notification tab NOT shown when both DETR and DSIL are refused."""
        # Create projet with both dotations
        projet = ProjetFactory(perimetre=collegue.perimetre)

        # Both refused
        detr_dotation = DotationProjetFactory(
            projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_REFUSED
        )

        DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_REFUSED
        )

        # Create simulation projet for DETR
        detr_enveloppe = DetrEnveloppeFactory(perimetre=collegue.perimetre)
        simulation = SimulationFactory(enveloppe=detr_enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation, simulation=simulation
        )

        # Get simulation projet detail page
        url = reverse(
            "simulation:simulation-projet-detail", kwargs={"pk": simulation_projet.id}
        )
        response = client_with_user_logged.get(url)

        assert response.status_code == 200
        # Check notification tab link is NOT present (none are accepted)
        assert "Notifications du demandeur" not in response.content.decode()
