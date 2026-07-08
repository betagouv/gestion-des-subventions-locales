"""
Tests for the inline notification-message form ("3 - Notifier" section of the
notifications tab), driven by ``NotificationMessageForm`` and posted through
``NotificationDocumentsView``.
"""

from typing import cast
from unittest import mock

import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_historique.models import ProjetAction
from gsl_notification.forms import NotificationMessageForm
from gsl_notification.tests.factories import AnnexeFactory, LettreEtArreteSignesFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL, PROJET_STATUS_ACCEPTED
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

    def test_post_without_htmx_header_is_rejected(
        self, client_with_user_logged, perimetre
    ):
        projet = _accepted_projet(perimetre)
        url = f"/notification/{projet.id}/notifier/"
        response = client_with_user_logged.post(url, {"message": "Bravo"})
        assert response.status_code == 400
