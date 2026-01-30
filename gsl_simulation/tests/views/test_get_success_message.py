"""
Tests for ProgrammationStatusUpdateView.get_success_message method.

This test file verifies that the get_success_message method returns
the correct success messages for all status combinations.
"""

from decimal import Decimal
from unittest import mock

import pytest

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
from gsl_simulation.views.simulation_projet_views import ProgrammationStatusUpdateView

pytestmark = pytest.mark.django_db

OTHER_DOTATION = {
    DOTATION_DSIL: DOTATION_DETR,
    DOTATION_DETR: DOTATION_DSIL,
}


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


def _create_view_instance(
    simulation_projet, status, new_project_status, client_with_user_logged
):
    """Helper to create a view instance with the necessary attributes."""
    view = ProgrammationStatusUpdateView()
    view.object = simulation_projet
    view.kwargs = {"status": status}
    view.new_project_status = new_project_status
    view.request = client_with_user_logged
    return view


def _call_get_success_message(view):
    """Helper to call get_success_message with a mock form (form parameter is not used)."""
    # The form parameter is required by the method signature but not used in the method body
    return view.get_success_message()


class TestGetSuccessMessageWhenSimpleDotation:
    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    def test_accepted_status(self, collegue, client_with_user_logged, dotation):
        """Test message when projet status is ACCEPTED."""
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("5000.00"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_ACCEPTED,
            PROJET_STATUS_PROCESSING,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été acceptée avec un montant de 5\xa0000,00\xa0€."
            == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    @pytest.mark.parametrize(
        "status, verbe",
        [
            (SimulationProjet.STATUS_REFUSED, "refusée"),
            (SimulationProjet.STATUS_DISMISSED, "classée sans suite"),
        ],
    )
    def test_processing_status_with_refused_or_dismissed_simulation_status(
        self,
        collegue,
        client_with_user_logged,
        dotation,
        status,
        verbe,
    ):
        """Test message when projet status is REFUSED or DISMISSED."""
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("5000.00"),
        )

        view = _create_view_instance(
            simulation_projet,
            status,
            PROJET_STATUS_REFUSED
            if status == SimulationProjet.STATUS_REFUSED
            else PROJET_STATUS_DISMISSED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été {verbe}. "
            f"Le dossier a bien été mis à jour sur Démarche Numérique." == message
        )


class TestGetSuccessMessageWhenDoubleDotation:
    """Test get_success_message when new_project_status is ACCEPTED."""

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    def test_with_accepted_status_when_other_dotation_is_accepted(
        self, collegue, client_with_user_logged, dotation
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_ACCEPTED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_ACCEPTED,
            PROJET_STATUS_ACCEPTED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été acceptée avec un montant de 7\xa0500,50\xa0€."
            == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    @pytest.mark.parametrize(
        "status, verbe",
        [
            (SimulationProjet.STATUS_REFUSED, "refusée"),
            (SimulationProjet.STATUS_DISMISSED, "classée sans suite"),
        ],
    )
    def test_with_refused_or_dismissed_status_when_other_dotation_is_accepted(
        self,
        collegue,
        client_with_user_logged,
        dotation,
        status,
        verbe,
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_ACCEPTED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            status,
            PROJET_STATUS_ACCEPTED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été {verbe}."
            == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    def test_with_accepted_status_when_other_dotation_is_refused(
        self, collegue, client_with_user_logged, dotation
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_REFUSED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_ACCEPTED,
            PROJET_STATUS_ACCEPTED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été acceptée avec un montant de 7\xa0500,50\xa0€."
            == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    def test_with_refused_status_when_other_dotation_is_refused(
        self, collegue, client_with_user_logged, dotation
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_REFUSED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_REFUSED,
            PROJET_STATUS_REFUSED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été refusée. "
            f"Le dossier a bien été mis à jour sur Démarche Numérique." == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    def test_with_dismissed_status_when_other_dotation_is_refused(
        self,
        collegue,
        client_with_user_logged,
        dotation,
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_REFUSED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_DISMISSED,
            PROJET_STATUS_DISMISSED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été classée sans suite. "
            f"Le dossier a bien été mis à jour sur Démarche Numérique." == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    def test_with_accepted_status_when_other_dotation_is_dismissed(
        self, collegue, client_with_user_logged, dotation
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_DISMISSED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_ACCEPTED,
            PROJET_STATUS_ACCEPTED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été acceptée avec un montant de 7\xa0500,50\xa0€."
            == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (
            DOTATION_DSIL,
            DOTATION_DETR,
        ),
    )
    def test_with_refused_status_when_other_dotation_is_dismissed(
        self, collegue, client_with_user_logged, dotation
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_DISMISSED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_REFUSED,
            PROJET_STATUS_DISMISSED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été refusée. "
            f"Sachant que la dotation {OTHER_DOTATION[dotation]} a été classée sans suite, le dossier a bien été classé sans suite sur Démarche Numérique."
            == message
        )

    @pytest.mark.parametrize(
        "dotation",
        (DOTATION_DSIL, DOTATION_DETR),
    )
    def test_with_dismissed_status_when_other_dotation_is_dismissed(
        self, collegue, client_with_user_logged, dotation
    ):
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        _other_dotation_projet = DotationProjetFactory(
            projet=projet,
            dotation=OTHER_DOTATION[dotation],
            status=PROJET_STATUS_DISMISSED,
        )
        dotation_projet = DotationProjetFactory(
            projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
        )
        enveloppe = (
            DsilEnveloppeFactory(perimetre=collegue.perimetre)
            if dotation == DOTATION_DSIL
            else DetrEnveloppeFactory(perimetre=collegue.perimetre)
        )
        simulation = SimulationFactory(enveloppe=enveloppe)
        simulation_projet = SimulationProjetFactory(
            dotation_projet=dotation_projet,
            simulation=simulation,
            status=SimulationProjet.STATUS_DISMISSED,
            montant=Decimal("7500.50"),
        )

        view = _create_view_instance(
            simulation_projet,
            SimulationProjet.STATUS_DISMISSED,
            PROJET_STATUS_DISMISSED,
            client_with_user_logged,
        )

        message = _call_get_success_message(view)

        assert (
            f"La demande de financement avec la dotation {dotation} a bien été classée sans suite. "
            f"Le dossier a bien été mis à jour sur Démarche Numérique." == message
        )
