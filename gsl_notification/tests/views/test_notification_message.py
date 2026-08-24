"""
Tests for the inline notification-message form ("3 - Notifier" section of the
notifications tab), driven by ``NotificationMessageForm`` and posted through
``NotificationDocumentsView``.
"""

import os
from typing import cast
from unittest import mock

import pytest
from django.utils import timezone

from gsl.historique.models import ProjetAction
from gsl_core.models import Collegue
from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_notification.forms import NotificationMessageForm
from gsl_notification.tests.factories import (
    AnnexeFactory,
    LettreEtArreteSignesFactory,
    LettreRefusSigneeFactory,
)
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

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre) -> Collegue:
    return cast(Collegue, CollegueWithDSProfileFactory(perimetre=perimetre))


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


def _accepted_dotation(perimetre, projet, dotation, with_signed_document):
    dp = DotationProjetFactory(
        projet=projet, dotation=dotation, status=PROJET_STATUS_ACCEPTED
    )
    enveloppe = (
        DetrEnveloppeFactory(perimetre=perimetre)
        if dotation == DOTATION_DETR
        else DsilEnveloppeFactory(perimetre=perimetre)
    )
    pp = ProgrammationProjetFactory(
        dotation_projet=dp,
        enveloppe=enveloppe,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    if with_signed_document:
        LettreEtArreteSignesFactory(programmation_projet=pp)
    return pp


def _accepted_projet(perimetre, dotation=DOTATION_DETR, with_signed_document=True):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    _accepted_dotation(perimetre, projet, dotation, with_signed_document)
    return projet


def _treated_dotation(perimetre, projet, dotation, status, with_signed_document=False):
    dp = DotationProjetFactory(projet=projet, dotation=dotation, status=status)
    enveloppe = (
        DetrEnveloppeFactory(perimetre=perimetre)
        if dotation == DOTATION_DETR
        else DsilEnveloppeFactory(perimetre=perimetre)
    )
    pp = ProgrammationProjetFactory(
        dotation_projet=dp, enveloppe=enveloppe, status=status
    )
    if with_signed_document:
        LettreRefusSigneeFactory(programmation_projet=pp)
    return pp


def _refused_projet(perimetre, dotation=DOTATION_DETR, with_signed_document=False):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    _treated_dotation(
        perimetre, projet, dotation, PROJET_STATUS_REFUSED, with_signed_document
    )
    return projet


def _dismissed_projet(perimetre, dotation=DOTATION_DETR, with_signed_document=False):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    _treated_dotation(
        perimetre, projet, dotation, PROJET_STATUS_DISMISSED, with_signed_document
    )
    return projet


class TestForm:
    def test_message_is_optional(self, perimetre):
        projet = _accepted_projet(perimetre)
        form = NotificationMessageForm(data={"message": ""}, instance=projet)
        assert form.is_valid()

    def test_clean_blocks_when_a_signed_document_is_missing(self, perimetre):
        projet = _accepted_projet(perimetre, with_signed_document=False)
        form = NotificationMessageForm(data={"message": ""}, instance=projet)
        assert not form.is_valid()
        assert form.non_field_errors()

    def test_save_sets_notified_at_and_creates_projet_action(self, perimetre, collegue):
        projet = _accepted_projet(perimetre)
        with (
            mock.patch("gsl_notification.forms.DsMutator.dossier_accepter") as ds,
            mock.patch("gsl_notification.forms.merge_documents_into_pdf"),
        ):
            form = NotificationMessageForm(data={"message": "Bravo"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        ds.assert_called_once()
        assert ds.call_args.kwargs["motivation"] == "Bravo"
        projet.refresh_from_db()
        assert projet.notified_at is not None
        assert ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_save_merges_documents_by_dotation_then_type(self, perimetre, collegue):
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        detr_pp = _accepted_dotation(
            perimetre, projet, DOTATION_DETR, with_signed_document=True
        )
        detr_annexe = AnnexeFactory(programmation_projet=detr_pp)
        dsil_pp = _accepted_dotation(
            perimetre, projet, DOTATION_DSIL, with_signed_document=True
        )
        dsil_annexe = AnnexeFactory(programmation_projet=dsil_pp)

        with (
            mock.patch("gsl_notification.forms.DsMutator.dossier_accepter"),
            mock.patch("gsl_notification.forms.merge_documents_into_pdf") as merge_mock,
        ):
            form = NotificationMessageForm(data={"message": ""}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        merged_documents = merge_mock.call_args.args[0]
        assert merged_documents == [
            detr_pp.lettre_et_arrete_signes,
            detr_annexe,
            dsil_pp.lettre_et_arrete_signes,
            dsil_annexe,
        ]

    def test_message_is_required_for_refused(self, perimetre):
        projet = _refused_projet(perimetre)
        form = NotificationMessageForm(data={"message": ""}, instance=projet)
        assert not form.is_valid()
        assert "message" in form.errors

    def test_message_is_required_for_dismissed(self, perimetre):
        projet = _dismissed_projet(perimetre)
        form = NotificationMessageForm(data={"message": ""}, instance=projet)
        assert not form.is_valid()
        assert "message" in form.errors

    def test_clean_does_not_block_refused_or_dismissed_without_signed_document(
        self, perimetre
    ):
        projet = _refused_projet(perimetre, with_signed_document=False)
        form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
        assert form.is_valid()

    def test_save_calls_refuser_in_ds_for_refused(self, perimetre, collegue):
        projet = _refused_projet(perimetre, with_signed_document=True)
        with (
            mock.patch("gsl_notification.forms.DsService.refuser_in_ds") as refuser,
            mock.patch("gsl_notification.forms.DsService.dismiss_in_ds") as dismiss,
            mock.patch("gsl_notification.forms.DsMutator.dossier_accepter") as accepter,
            mock.patch("gsl_notification.forms.merge_documents_into_pdf"),
        ):
            form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        refuser.assert_called_once()
        assert refuser.call_args.kwargs["motivation"] == "Motif"
        dismiss.assert_not_called()
        accepter.assert_not_called()

    def test_save_calls_dismiss_in_ds_for_dismissed(self, perimetre, collegue):
        projet = _dismissed_projet(perimetre, with_signed_document=True)
        with (
            mock.patch("gsl_notification.forms.DsService.dismiss_in_ds") as dismiss,
            mock.patch("gsl_notification.forms.DsService.refuser_in_ds") as refuser,
            mock.patch("gsl_notification.forms.DsMutator.dossier_accepter") as accepter,
            mock.patch("gsl_notification.forms.merge_documents_into_pdf"),
        ):
            form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        dismiss.assert_called_once()
        assert dismiss.call_args.kwargs["motivation"] == "Motif"
        refuser.assert_not_called()
        accepter.assert_not_called()

    def test_save_passes_none_document_when_no_imported_documents(
        self, perimetre, collegue
    ):
        projet = _refused_projet(perimetre, with_signed_document=False)
        with (
            mock.patch("gsl_notification.forms.DsService.refuser_in_ds") as refuser,
            mock.patch("gsl_notification.forms.merge_documents_into_pdf") as merge_mock,
        ):
            form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        merge_mock.assert_not_called()
        assert refuser.call_args.kwargs["document"] is None

    def test_save_merges_lettre_refus_signee_and_annexe_for_refused(
        self, perimetre, collegue
    ):
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        pp = _treated_dotation(
            perimetre,
            projet,
            DOTATION_DETR,
            PROJET_STATUS_REFUSED,
            with_signed_document=True,
        )
        annexe = AnnexeFactory(programmation_projet=pp)

        with (
            mock.patch("gsl_notification.forms.DsService.refuser_in_ds"),
            mock.patch("gsl_notification.forms.merge_documents_into_pdf") as merge_mock,
        ):
            form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        merged_documents = merge_mock.call_args.args[0]
        assert merged_documents == [pp.lettre_refus_signee, annexe]

    def test_notification_filename_single_document_uses_its_own_name(self, perimetre):
        projet = _refused_projet(perimetre, with_signed_document=True)
        documents = projet.imported_documents
        filename = NotificationMessageForm(instance=projet)._notification_filename(
            documents
        )
        assert filename == os.path.splitext(documents[0].name)[0] + ".pdf"

    def test_notification_filename_multiple_documents_lists_contributing_dotations(
        self, perimetre
    ):
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        _treated_dotation(
            perimetre,
            projet,
            DOTATION_DETR,
            PROJET_STATUS_REFUSED,
            with_signed_document=True,
        )
        _treated_dotation(
            perimetre,
            projet,
            DOTATION_DSIL,
            PROJET_STATUS_DISMISSED,
            with_signed_document=True,
        )

        documents = projet.imported_documents
        filename = NotificationMessageForm(instance=projet)._notification_filename(
            documents
        )
        ds_number = projet.dossier_ds.ds_number
        assert filename == f"Notification {ds_number} DETR-DSIL.pdf"

    def test_save_picks_optimistic_dismiss_for_mixed_refused_dismissed_double_dotation(
        self, perimetre, collegue
    ):
        """REFUSED + DISMISSED resolves to DISMISSED (optimistic)."""
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        _treated_dotation(perimetre, projet, DOTATION_DETR, PROJET_STATUS_REFUSED)
        _treated_dotation(perimetre, projet, DOTATION_DSIL, PROJET_STATUS_DISMISSED)

        with (
            mock.patch("gsl_notification.forms.DsService.dismiss_in_ds") as dismiss,
            mock.patch("gsl_notification.forms.DsService.refuser_in_ds") as refuser,
        ):
            form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        dismiss.assert_called_once()
        refuser.assert_not_called()


class TestView:
    def test_post_send_notification_success(self, client_with_user_logged, perimetre):
        projet = _accepted_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/"
        with (
            mock.patch("gsl_notification.forms.DsMutator.dossier_accepter"),
            mock.patch("gsl_notification.forms.merge_documents_into_pdf"),
        ):
            response = client_with_user_logged.post(
                url, {"message": "Bravo"}, headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        assert response.headers.get("HX-Refresh") == "true"
        projet.refresh_from_db()
        assert projet.notified_at is not None
        assert ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_send_notification_blocked_when_document_missing(
        self, client_with_user_logged, perimetre
    ):
        projet = _accepted_projet(perimetre, with_signed_document=False)
        url = f"/notification/{projet.id}/notifier/"
        response = client_with_user_logged.post(
            url, {"message": ""}, headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        projet.refresh_from_db()
        assert projet.notified_at is None
        assert not ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_send_notification_success_for_refused(
        self, client_with_user_logged, perimetre
    ):
        projet = _refused_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/"
        with mock.patch("gsl_notification.forms.DsService.refuser_in_ds"):
            response = client_with_user_logged.post(
                url, {"message": "Motif"}, headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        assert response.headers.get("HX-Refresh") == "true"
        projet.refresh_from_db()
        assert projet.notified_at is not None
        assert ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_send_notification_success_for_dismissed(
        self, client_with_user_logged, perimetre
    ):
        projet = _dismissed_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/"
        with mock.patch("gsl_notification.forms.DsService.dismiss_in_ds"):
            response = client_with_user_logged.post(
                url, {"message": "Motif"}, headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        assert response.headers.get("HX-Refresh") == "true"
        projet.refresh_from_db()
        assert projet.notified_at is not None
        assert ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_send_notification_blocked_when_message_missing_for_refused(
        self, client_with_user_logged, perimetre
    ):
        projet = _refused_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/"
        response = client_with_user_logged.post(
            url, {"message": ""}, headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        projet.refresh_from_db()
        assert projet.notified_at is None
        assert not ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_send_notification_blocked_when_message_missing_for_dismissed(
        self, client_with_user_logged, perimetre
    ):
        projet = _dismissed_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/"
        response = client_with_user_logged.post(
            url, {"message": ""}, headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        projet.refresh_from_db()
        assert projet.notified_at is None
        assert not ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_without_htmx_header_is_rejected(
        self, client_with_user_logged, perimetre
    ):
        projet = _accepted_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/"
        response = client_with_user_logged.post(url, {"message": "Bravo"})
        assert response.status_code == 400

    def test_view_excludes_projets_with_a_dotation_still_processing(
        self, client_with_user_logged, perimetre
    ):
        """One dotation still being processed means the projet isn't notifiable yet."""
        projet = _accepted_projet(perimetre, dotation=DOTATION_DETR)
        DotationProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_PROCESSING
        )

        url = f"/notification/{projet.id}/notifier/"
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})
        assert response.status_code == 404

    def test_view_excludes_already_notified_projets(
        self, client_with_user_logged, perimetre
    ):
        projet = _accepted_projet(perimetre)
        projet.notified_at = timezone.now()
        projet.save()

        url = f"/notification/{projet.id}/notifier/"
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})
        assert response.status_code == 404
