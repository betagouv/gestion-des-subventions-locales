"""
Tests for the inline notification-message form ("3 - Notifier" section of the
notifications tab), driven by ``NotificationMessageForm`` and posted through
``NotificationDocumentsView``.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from gsl.core.models import Collegue
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl.historique.models import ProjetAction
from gsl.historique.tests.factories import ProjetActionFactory
from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from gsl.projet.tests.factories import EnveloppeProjetFactory, ProjetFactory
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import (
    DossierDataFactory,
    DossierFactory,
)
from gsl_notification.forms import NotificationMessageForm
from gsl_notification.tests.factories import (
    AnnexeFactory,
    LettreEtArreteSignesFactory,
    LettreRefusSigneeFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

DS_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "gsl_demarches_simplifiees"
    / "tests"
    / "ds_fixtures"
)


def _full_ds_dossier_data() -> dict:
    with open(DS_FIXTURES_DIR / "dossier_data.json") as handle:
        return json.loads(handle.read())


def _ds_mutation_response(
    mutation_key: str,
    *,
    state: str,
    event: str,
    date_traitement: str,
    traitement_id: str = "traitement-1",
) -> dict:
    return {
        "data": {
            mutation_key: {
                "dossier": {
                    "dateTraitement": date_traitement,
                    "state": state,
                    "traitements": [
                        {
                            "id": traitement_id,
                            "dateTraitement": date_traitement,
                            "event": event,
                        }
                    ],
                }
            }
        }
    }


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
    enveloppe = (
        DetrEnveloppeFactory(perimetre=perimetre)
        if dotation == DOTATION_DETR
        else DsilEnveloppeFactory(perimetre=perimetre)
    )
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet,
        dotation=dotation,
        status=ProjetStatus.ACCEPTED,
        enveloppe=enveloppe,
    )
    if with_signed_document:
        LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)
    return enveloppe_projet


def _accepted_projet(perimetre, dotation=DOTATION_DETR, with_signed_document=True):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    _accepted_dotation(perimetre, projet, dotation, with_signed_document)
    return projet


def _treated_dotation(perimetre, projet, dotation, status, with_signed_document=False):
    enveloppe = (
        DetrEnveloppeFactory(perimetre=perimetre)
        if dotation == DOTATION_DETR
        else DsilEnveloppeFactory(perimetre=perimetre)
    )
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=dotation, status=status, enveloppe=enveloppe
    )
    if with_signed_document:
        LettreRefusSigneeFactory(enveloppe_projet=enveloppe_projet)
    return enveloppe_projet


def _refused_projet(perimetre, dotation=DOTATION_DETR, with_signed_document=False):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    _treated_dotation(
        perimetre, projet, dotation, ProjetStatus.REFUSED, with_signed_document
    )
    return projet


def _dismissed_projet(perimetre, dotation=DOTATION_DETR, with_signed_document=False):
    projet = ProjetFactory(dossier_ds__perimetre=perimetre)
    _treated_dotation(
        perimetre, projet, dotation, ProjetStatus.DISMISSED, with_signed_document
    )
    return projet


def _merged_pdf():
    """A stand-in for the real ``merge_documents_into_pdf`` return value:
    ``form.save()`` reads and re-saves it, so a plain Mock won't do."""
    return SimpleUploadedFile(
        "notification.pdf", b"%PDF-1.4 fake content", content_type="application/pdf"
    )


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

    def test_save_sets_notified_at(self, perimetre, collegue):
        dossier = DossierFactory(
            perimetre=perimetre,
            porteur_de_projet_arrondissement=None,
            porteur_de_projet_departement=perimetre.departement,
        )
        DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
        projet = ProjetFactory(dossier_ds=dossier)
        _accepted_dotation(perimetre, projet, DOTATION_DETR, with_signed_document=True)

        dn_date_traitement = timezone.now().isoformat()

        with (
            mock.patch(
                "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_accepter",
                return_value=_ds_mutation_response(
                    "dossierAccepter",
                    state="accepte",
                    event="accepte",
                    date_traitement=dn_date_traitement,
                ),
            ) as ds,
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ),
        ):
            form = NotificationMessageForm(data={"message": "Bravo"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        ds.assert_called_once()
        assert ds.call_args.kwargs["motivation"] == "Bravo"
        projet.refresh_from_db()
        assert projet.notified_at is not None

    def test_save_uses_dn_date_traitement_for_notified_at(self, perimetre, collegue):
        dossier = DossierFactory(
            perimetre=perimetre,
            porteur_de_projet_arrondissement=None,
            porteur_de_projet_departement=perimetre.departement,
        )
        DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
        projet = ProjetFactory(dossier_ds=dossier)
        _accepted_dotation(perimetre, projet, DOTATION_DETR, with_signed_document=True)

        dn_date_traitement = datetime(2025, 6, 25, 11, 46, 30, tzinfo=UTC)

        with (
            mock.patch(
                "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_accepter",
                return_value=_ds_mutation_response(
                    "dossierAccepter",
                    state="accepte",
                    event="accepte",
                    date_traitement=dn_date_traitement.isoformat(),
                ),
            ),
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ),
        ):
            form = NotificationMessageForm(data={"message": "Bravo"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        projet.refresh_from_db()
        assert projet.notified_at == dn_date_traitement

    def test_save_passer_en_instruction_first_does_not_change_dotation_status(
        self, perimetre, collegue
    ):
        dossier = DossierFactory(
            perimetre=perimetre,
            porteur_de_projet_arrondissement=None,
            porteur_de_projet_departement=perimetre.departement,
            ds_state=Dossier.STATE_EN_CONSTRUCTION,
        )
        full_raw_data = _full_ds_dossier_data()
        assert full_raw_data["state"] == "en_construction"
        DossierDataFactory(dossier=dossier, raw_data=full_raw_data)
        projet = ProjetFactory(dossier_ds=dossier)
        enveloppe_projet = _accepted_dotation(
            perimetre, projet, DOTATION_DETR, with_signed_document=True
        )

        with (
            mock.patch(
                "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_passer_en_instruction",
                return_value={
                    "data": {
                        "dossierPasserEnInstruction": {
                            "dossier": {
                                "state": "en_instruction",
                                "traitements": [
                                    {
                                        "id": "traitement-passage",
                                        "event": "passe_en_instruction",
                                    }
                                ],
                            }
                        }
                    }
                },
            ) as passer_en_instruction,
            mock.patch(
                "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_accepter",
                return_value=_ds_mutation_response(
                    "dossierAccepter",
                    state="accepte",
                    event="accepte",
                    date_traitement=timezone.now().isoformat(),
                ),
            ),
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ),
        ):
            form = NotificationMessageForm(data={"message": "Bravo"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        passer_en_instruction.assert_called_once()
        enveloppe_projet.refresh_from_db()
        assert enveloppe_projet.status == ProjetStatus.ACCEPTED
        projet.refresh_from_db()
        assert projet.notified_at is not None

        actions = ProjetAction.objects.filter(projet=projet)
        assert actions.count() == 2
        assert {a.action_type for a in actions} == {
            ProjetAction.TYPE_PASSAGE_EN_INSTRUCTION,
            ProjetAction.TYPE_NOTIFIED,
        }

    def test_save_merges_documents_by_dotation_then_type(self, perimetre, collegue):
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        detr_enveloppe_projet = _accepted_dotation(
            perimetre, projet, DOTATION_DETR, with_signed_document=True
        )
        detr_annexe = AnnexeFactory(enveloppe_projet=detr_enveloppe_projet)
        dsil_enveloppe_projet = _accepted_dotation(
            perimetre, projet, DOTATION_DSIL, with_signed_document=True
        )
        dsil_annexe = AnnexeFactory(enveloppe_projet=dsil_enveloppe_projet)

        with (
            mock.patch(
                "gsl_notification.forms.DsService.accept_in_ds", return_value=None
            ),
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ) as merge_mock,
        ):
            form = NotificationMessageForm(data={"message": ""}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        merged_documents = merge_mock.call_args.args[0]
        assert merged_documents == [
            detr_enveloppe_projet.lettre_et_arrete_signes,
            detr_annexe,
            dsil_enveloppe_projet.lettre_et_arrete_signes,
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
            mock.patch(
                "gsl_notification.forms.DsService.refuser_in_ds", return_value=None
            ) as refuser,
            mock.patch(
                "gsl_notification.forms.DsService.dismiss_in_ds", return_value=None
            ) as dismiss,
            mock.patch(
                "gsl_notification.forms.DsService.accept_in_ds", return_value=None
            ) as accepter,
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ),
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
            mock.patch(
                "gsl_notification.forms.DsService.dismiss_in_ds", return_value=None
            ) as dismiss,
            mock.patch(
                "gsl_notification.forms.DsService.refuser_in_ds", return_value=None
            ) as refuser,
            mock.patch(
                "gsl_notification.forms.DsService.accept_in_ds", return_value=None
            ) as accepter,
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ),
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
            mock.patch(
                "gsl_notification.forms.DsService.refuser_in_ds", return_value=None
            ) as refuser,
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
        enveloppe_projet = _treated_dotation(
            perimetre,
            projet,
            DOTATION_DETR,
            ProjetStatus.REFUSED,
            with_signed_document=True,
        )
        annexe = AnnexeFactory(enveloppe_projet=enveloppe_projet)

        with (
            mock.patch(
                "gsl_notification.forms.DsService.refuser_in_ds", return_value=None
            ),
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ) as merge_mock,
        ):
            form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        merged_documents = merge_mock.call_args.args[0]
        assert merged_documents == [enveloppe_projet.lettre_refus_signee, annexe]

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
            ProjetStatus.REFUSED,
            with_signed_document=True,
        )
        _treated_dotation(
            perimetre,
            projet,
            DOTATION_DSIL,
            ProjetStatus.DISMISSED,
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
        _treated_dotation(perimetre, projet, DOTATION_DETR, ProjetStatus.REFUSED)
        _treated_dotation(perimetre, projet, DOTATION_DSIL, ProjetStatus.DISMISSED)

        with (
            mock.patch(
                "gsl_notification.forms.DsService.dismiss_in_ds", return_value=None
            ) as dismiss,
            mock.patch(
                "gsl_notification.forms.DsService.refuser_in_ds", return_value=None
            ) as refuser,
        ):
            form = NotificationMessageForm(data={"message": "Motif"}, instance=projet)
            assert form.is_valid()
            form.save(user=collegue)

        dismiss.assert_called_once()
        refuser.assert_not_called()


class TestView:
    def test_post_send_notification_success(self, client_with_user_logged, perimetre):
        """Real end-to-end: only the DN network call is faked.
        DsService.accept_in_ds and refresh_dossier_from_saved_data both run
        for real — including ProjetService.create_or_update_from_ds_dossier,
        which is what actually sets notified_at once it sees the dossier's
        DS state as treated. notified_at itself is never mocked: this is
        what proves the real chain, end to end, does update it."""
        dossier = DossierFactory(
            perimetre=perimetre,
            porteur_de_projet_arrondissement=None,
            porteur_de_projet_departement=perimetre.departement,
        )
        DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
        projet = ProjetFactory(dossier_ds=dossier)
        _accepted_dotation(perimetre, projet, DOTATION_DETR, with_signed_document=True)

        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
        dn_date_traitement = timezone.now().isoformat()

        with (
            mock.patch(
                "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_accepter",
                return_value=_ds_mutation_response(
                    "dossierAccepter",
                    state="accepte",
                    event="accepte",
                    date_traitement=dn_date_traitement,
                ),
            ),
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ),
        ):
            response = client_with_user_logged.post(
                url, {"message": "Bravo"}, headers={"HX-Request": "true"}
            )
        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="notification-message-block"' in content
        assert 'id="notified-block"' in content
        assert 'id="projet-actions"' in content
        assert 'id="generate-documents-block"' in content
        # Regression: the tab's other form fragment tags (generate_documents_form,
        # notification_message_form) share this same POST request. Without
        # forcing it back to GET semantics before re-rendering the tab, they'd
        # bind to this notify form's body and render as invalid.
        assert "fr-error-text" not in content
        projet.refresh_from_db()
        assert projet.notified_at is not None
        # The "4 - Notifications" block lists this notification's details.
        assert "Bravo" in content

    def test_notifications_are_listed_chronologically_across_renotifications(
        self, client_with_user_logged, perimetre
    ):
        dossier = DossierFactory(
            perimetre=perimetre,
            porteur_de_projet_arrondissement=None,
            porteur_de_projet_departement=perimetre.departement,
        )
        DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
        projet = ProjetFactory(dossier_ds=dossier)
        _accepted_dotation(perimetre, projet, DOTATION_DETR, with_signed_document=True)

        first_date_traitement = datetime(2025, 6, 25, 11, 46, 30, tzinfo=UTC)
        ProjetActionFactory(
            projet=projet,
            source_id="traitement-1",
            action_type=ProjetAction.TYPE_NOTIFIED,
            created_at=first_date_traitement,
            details="Premier message",
        )
        # notified_at stays None here: a dotation change reset it since that
        # first notification, which is exactly what allows re-notifying.

        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
        second_date_traitement = datetime(2025, 6, 26, 9, 0, 0, tzinfo=UTC)

        with (
            mock.patch(
                "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_accepter",
                return_value=_ds_mutation_response(
                    "dossierAccepter",
                    state="accepte",
                    event="accepte",
                    date_traitement=second_date_traitement.isoformat(),
                    traitement_id="traitement-2",
                ),
            ),
            mock.patch(
                "gsl_notification.forms.merge_documents_into_pdf",
                return_value=_merged_pdf(),
            ),
        ):
            response = client_with_user_logged.post(
                url, {"message": "Second message"}, headers={"HX-Request": "true"}
            )

        assert response.status_code == 200
        content = response.content.decode()
        assert content.index("Premier message") < content.index("Second message")
        assert (
            ProjetAction.objects.filter(
                projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
            ).count()
            == 2
        )
        projet.refresh_from_db()
        assert projet.notified_at == second_date_traitement

    def test_post_send_notification_blocked_when_document_missing(
        self, client_with_user_logged, perimetre
    ):
        projet = _accepted_projet(perimetre, with_signed_document=False)
        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
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
        dossier = DossierFactory(
            perimetre=perimetre,
            porteur_de_projet_arrondissement=None,
            porteur_de_projet_departement=perimetre.departement,
        )
        DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
        projet = ProjetFactory(dossier_ds=dossier)
        _treated_dotation(perimetre, projet, DOTATION_DETR, ProjetStatus.REFUSED)

        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
        dn_date_traitement = timezone.now().isoformat()

        with mock.patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_refuser",
            return_value=_ds_mutation_response(
                "dossierRefuser",
                state="refuse",
                event="refuse",
                date_traitement=dn_date_traitement,
            ),
        ):
            response = client_with_user_logged.post(
                url, {"message": "Motif"}, headers={"HX-Request": "true"}
            )

        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="notification-message-block"' in content
        assert 'id="notified-block"' in content
        projet.refresh_from_db()
        assert projet.notified_at is not None
        assert ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_send_notification_success_for_dismissed(
        self, client_with_user_logged, perimetre
    ):
        dossier = DossierFactory(
            perimetre=perimetre,
            porteur_de_projet_arrondissement=None,
            porteur_de_projet_departement=perimetre.departement,
        )
        DossierDataFactory(dossier=dossier, raw_data=_full_ds_dossier_data())
        projet = ProjetFactory(dossier_ds=dossier)
        _treated_dotation(perimetre, projet, DOTATION_DETR, ProjetStatus.DISMISSED)

        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
        dn_date_traitement = timezone.now().isoformat()

        with mock.patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_classer_sans_suite",
            return_value=_ds_mutation_response(
                "dossierClasserSansSuite",
                state="sans_suite",
                event="classe_sans_suite",
                date_traitement=dn_date_traitement,
            ),
        ):
            response = client_with_user_logged.post(
                url, {"message": "Motif"}, headers={"HX-Request": "true"}
            )

        assert response.status_code == 200
        content = response.content.decode()
        assert 'id="notification-message-block"' in content
        assert 'id="notified-block"' in content
        projet.refresh_from_db()
        assert projet.notified_at is not None
        assert ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_NOTIFIED
        ).exists()

    def test_post_send_notification_blocked_when_message_missing_for_refused(
        self, client_with_user_logged, perimetre
    ):
        projet = _refused_projet(perimetre)
        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
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
        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
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
        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
        response = client_with_user_logged.post(url, {"message": "Bravo"})
        assert response.status_code == 400

    def test_view_excludes_projets_with_a_dotation_still_processing(
        self, client_with_user_logged, perimetre
    ):
        """One dotation still being processed means the projet isn't notifiable yet."""
        projet = _accepted_projet(perimetre, dotation=DOTATION_DETR)
        EnveloppeProjetFactory(
            projet=projet, dotation=DOTATION_DSIL, status=ProjetStatus.PROCESSING
        )

        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
        response = client_with_user_logged.post(url, headers={"HX-Request": "true"})
        assert response.status_code == 404

    def test_view_excludes_already_notified_projets(
        self, client_with_user_logged, perimetre
    ):
        projet = _accepted_projet(perimetre)
        projet.notified_at = timezone.now()
        projet.save()

        url = reverse(
            "fragment:gsl_notification:notification_message",
            kwargs={"pk": projet.id},
        )
        response = client_with_user_logged.post(url, headers={"HX-Request": "true"})
        assert response.status_code == 404
