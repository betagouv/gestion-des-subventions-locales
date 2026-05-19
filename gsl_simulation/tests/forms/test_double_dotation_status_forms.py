"""
Tests for double dotation status changes.

These tests verify that when a project has both DETR and DSIL dotations,
status changes work correctly for each dotation independently. Notification
to DN is now a separate step (see gsl_notification tests), so even when all
dotations resolve to refused/dismissed, the status-change form must not
touch DN nor set ``projet.notified_at``.
"""

from typing import cast
from unittest import mock

import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import CollegueFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.forms import SimulationProjetStatusForm
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> Collegue:
    return cast(Collegue, CollegueFactory())


@pytest.fixture
def double_dotation_projet_detr_dsil():
    """Create a projet with both DETR and DSIL dotations in PROCESSING state."""
    projet = ProjetFactory()
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


class TestRefuseOneDoubleDotation:
    """Refusing one dotation never notifies DN at status-change time."""

    def test_refuse_detr_when_dsil_processing(
        self, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        form = SimulationProjetStatusForm(
            instance=detr_simulation_projet, status=SimulationProjet.STATUS_REFUSED
        )
        form.save(user)

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_REFUSED
        assert dsil_dotation.status == PROJET_STATUS_PROCESSING
        assert projet.status == PROJET_STATUS_PROCESSING
        assert projet.notified_at is None

    def test_refuse_detr_when_dsil_already_refused(
        self, double_dotation_projet_detr_dsil, user
    ):
        """Even when both dotations end up refused, no DS push at status time."""
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        dsil_dotation.status = PROJET_STATUS_REFUSED
        dsil_dotation.save()

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        with mock.patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_refuser"
        ) as mock_ds_refuser:
            form = SimulationProjetStatusForm(
                instance=detr_simulation_projet,
                status=SimulationProjet.STATUS_REFUSED,
            )
            form.save(user)
            mock_ds_refuser.assert_not_called()

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_REFUSED
        assert dsil_dotation.status == PROJET_STATUS_REFUSED
        assert projet.status == PROJET_STATUS_REFUSED
        assert projet.notified_at is None

    def test_refuse_detr_when_dsil_accepted(
        self, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        dsil_dotation.status = PROJET_STATUS_ACCEPTED
        dsil_dotation.save()

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        form = SimulationProjetStatusForm(
            instance=detr_simulation_projet, status=SimulationProjet.STATUS_REFUSED
        )
        form.save(user)

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_REFUSED
        assert dsil_dotation.status == PROJET_STATUS_ACCEPTED
        assert projet.status == PROJET_STATUS_ACCEPTED
        assert projet.notified_at is None


class TestDismissOneDoubleDotation:
    """Dismissing one dotation never notifies DN at status-change time."""

    def test_dismiss_dsil_when_detr_processing(
        self, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        form = SimulationProjetStatusForm(
            instance=dsil_simulation_projet, status=SimulationProjet.STATUS_DISMISSED
        )
        form.save(user)

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_PROCESSING
        assert dsil_dotation.status == PROJET_STATUS_DISMISSED
        assert projet.status == PROJET_STATUS_PROCESSING
        assert projet.notified_at is None

    def test_dismiss_dsil_when_detr_dismissed(
        self, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        detr_dotation.status = PROJET_STATUS_DISMISSED
        detr_dotation.save()
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        ProgrammationProjetFactory(
            dotation_projet=detr_dotation, enveloppe=detr_enveloppe
        )

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        with mock.patch(
            "gsl_demarches_simplifiees.services.DsService.dismiss_in_ds"
        ) as mock_ds_dismiss:
            form = SimulationProjetStatusForm(
                instance=dsil_simulation_projet,
                status=SimulationProjet.STATUS_DISMISSED,
            )
            form.save(user)
            mock_ds_dismiss.assert_not_called()

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_DISMISSED
        assert dsil_dotation.status == PROJET_STATUS_DISMISSED
        assert projet.status == PROJET_STATUS_DISMISSED
        assert projet.notified_at is None

    def test_dismiss_dsil_when_detr_refused(
        self, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        detr_dotation.status = PROJET_STATUS_REFUSED
        detr_dotation.save()
        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        ProgrammationProjetFactory(
            dotation_projet=detr_dotation, enveloppe=detr_enveloppe
        )

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        with mock.patch(
            "gsl_demarches_simplifiees.services.DsService.dismiss_in_ds"
        ) as mock_ds_dismiss:
            form = SimulationProjetStatusForm(
                instance=dsil_simulation_projet,
                status=SimulationProjet.STATUS_DISMISSED,
            )
            form.save(user)
            mock_ds_dismiss.assert_not_called()

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_REFUSED
        assert dsil_dotation.status == PROJET_STATUS_DISMISSED
        assert projet.status == PROJET_STATUS_DISMISSED
        assert projet.notified_at is None


class TestAcceptOneDoubleDotation:
    """Accepting still updates DS annotations because that's a per-dotation push,
    not the applicant-facing notification."""

    @mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    )
    def test_accept_detr_leaves_dsil_processing(
        self, mock_ds_update, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        form = SimulationProjetStatusForm(
            instance=detr_simulation_projet, status=SimulationProjet.STATUS_ACCEPTED
        )
        form.save(user)

        mock_ds_update.assert_called_once_with(
            dossier=projet.dossier_ds,
            user=user,
            dotations_to_be_checked=[DOTATION_DETR],
            annotations_dotation_to_update=DOTATION_DETR,
            assiette=detr_dotation.assiette,
            montant=detr_simulation_projet.montant,
            taux=detr_simulation_projet.taux,
        )

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_ACCEPTED
        assert dsil_dotation.status == PROJET_STATUS_PROCESSING
        assert projet.status == PROJET_STATUS_PROCESSING

        assert ProgrammationProjet.objects.filter(
            dotation_projet=detr_dotation
        ).exists()
        assert not ProgrammationProjet.objects.filter(
            dotation_projet=dsil_dotation
        ).exists()

    @mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    )
    def test_accept_both_dotations_separately(
        self, mock_ds_update, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        form_detr = SimulationProjetStatusForm(
            instance=detr_simulation_projet, status=SimulationProjet.STATUS_ACCEPTED
        )
        form_detr.save(user)

        projet.refresh_from_db()
        assert projet.status == PROJET_STATUS_PROCESSING

        form_dsil = SimulationProjetStatusForm(
            instance=dsil_simulation_projet, status=SimulationProjet.STATUS_ACCEPTED
        )
        form_dsil.save(user)

        assert mock_ds_update.call_count == 2

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_ACCEPTED
        assert dsil_dotation.status == PROJET_STATUS_ACCEPTED
        assert projet.status == PROJET_STATUS_ACCEPTED

        assert ProgrammationProjet.objects.filter(
            dotation_projet=detr_dotation
        ).exists()
        assert ProgrammationProjet.objects.filter(
            dotation_projet=dsil_dotation
        ).exists()

    @mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    )
    def test_accept_detr_when_dsil_refused_projet_becomes_accepted(
        self, mock_ds_update, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        dsil_dotation.status = PROJET_STATUS_REFUSED
        dsil_dotation.save()

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        form = SimulationProjetStatusForm(
            instance=detr_simulation_projet, status=SimulationProjet.STATUS_ACCEPTED
        )
        form.save(user)

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_ACCEPTED
        assert dsil_dotation.status == PROJET_STATUS_REFUSED
        assert projet.status == PROJET_STATUS_ACCEPTED


class TestSetBackToProcessing:
    """Setting one dotation back to processing removes its programmation."""

    def test_set_back_to_processing_removes_programmation_for_one_dotation(
        self, double_dotation_projet_detr_dsil, user
    ):
        detr_dotation = double_dotation_projet_detr_dsil["detr_dotation"]
        dsil_dotation = double_dotation_projet_detr_dsil["dsil_dotation"]
        projet = double_dotation_projet_detr_dsil["projet"]

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )
        SimulationProjetStatusForm(
            instance=detr_simulation_projet, status=SimulationProjet.STATUS_REFUSED
        ).save(user)

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )
        SimulationProjetStatusForm(
            instance=dsil_simulation_projet, status=SimulationProjet.STATUS_REFUSED
        ).save(user)

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_REFUSED
        assert dsil_dotation.status == PROJET_STATUS_REFUSED
        assert projet.status == PROJET_STATUS_REFUSED
        assert ProgrammationProjet.objects.filter(
            dotation_projet=detr_dotation
        ).exists()
        assert ProgrammationProjet.objects.filter(
            dotation_projet=dsil_dotation
        ).exists()
        # No notification happens at status-change time anymore.
        assert projet.notified_at is None

        detr_simulation_projet.refresh_from_db()

        with mock.patch(
            "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
        ):
            with mock.patch(
                "gsl_demarches_simplifiees.services.DsService.repasser_en_instruction"
            ):
                SimulationProjetStatusForm(
                    instance=detr_simulation_projet,
                    status=SimulationProjet.STATUS_PROCESSING,
                ).save(user)

        assert not ProgrammationProjet.objects.filter(
            dotation_projet=detr_dotation
        ).exists()
        assert ProgrammationProjet.objects.filter(
            dotation_projet=dsil_dotation
        ).exists()

        detr_dotation.refresh_from_db()
        dsil_dotation.refresh_from_db()
        projet.refresh_from_db()

        assert detr_dotation.status == PROJET_STATUS_PROCESSING
        assert dsil_dotation.status == PROJET_STATUS_REFUSED
        assert projet.status == PROJET_STATUS_PROCESSING
        assert projet.notified_at is None


# Silence unused-import warnings for the factory used only in fixtures above.
_ = DotationProjetFactory
