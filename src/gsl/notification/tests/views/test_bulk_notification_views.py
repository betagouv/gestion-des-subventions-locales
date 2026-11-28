from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from dn.sync.exceptions import DsServiceException
from dn.sync.models import Dotation
from gsl.core.models import BulkActionsJob
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl.notification.models import UploadedDocument
from gsl.notification.tasks import run_bulk_notification_job
from gsl.notification.tests.factories import LettreEtArreteSignesFactory
from gsl.programmation.constants import BulkAction
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.projet.constants import ProjetStatus
from gsl.projet.tests.factories import EnveloppeProjetFactory

pytestmark = pytest.mark.django_db

HTMX_HEADERS = {"HTTP_HX_REQUEST": "true"}
REFUS = "refus"
ACCEPTED = "accepted"


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre):
    return CollegueWithDSProfileFactory(perimetre=perimetre)


@pytest.fixture
def client(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def detr_enveloppe(perimetre):
    return DetrEnveloppeFactory(perimetre=perimetre)


@pytest.fixture
def make_enveloppe_projet(perimetre, detr_enveloppe, collegue):
    def make(
        status=ProjetStatus.REFUSED,
        instructeur=True,
        notified_at=None,
        signed=False,
        **kwargs,
    ):
        enveloppe_projet = EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=perimetre,
            projet__notified_at=notified_at,
            dotation=Dotation.DETR,
            enveloppe=detr_enveloppe,
            status=status,
            **kwargs,
        )
        if instructeur:
            enveloppe_projet.projet.dossier_ds.ds_instructeurs.add(collegue.ds_profile)
        if signed:
            LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)
        return enveloppe_projet

    return make


@pytest.fixture
def dn():
    with (
        mock.patch("dn.sync.services.DsService.passer_en_instruction"),
        mock.patch("dn.sync.services.DsService.refuser") as refuser,
        mock.patch("dn.sync.services.DsService.classer_sans_suite") as dismiss,
        mock.patch("dn.sync.services.DsService.accepter") as accepter,
        mock.patch(
            "gsl.projet.models.mixins.merge_documents_into_pdf",
            return_value=mock.sentinel.merged_pdf,
        ),
    ):
        yield mock.Mock(refuser=refuser, classer_sans_suite=dismiss, accepter=accepter)


def _post_step(client, step, fields, kind=REFUS):
    action = f"notify_{kind}"
    data = {f"{action}_{Dotation.DETR}-current_step": step}
    data.update({f"{step}-{key}": value for key, value in fields.items()})
    return client.post(
        reverse("bulk-action", args=[Dotation.DETR, action]),
        data,
        **HTMX_HEADERS,
    )


def _post_launch(client, *enveloppe_projets, kind=REFUS):
    ids = ",".join(str(enveloppe_projet.pk) for enveloppe_projet in enveloppe_projets)
    return _post_step(client, "launch", {"ids": ids}, kind=kind)


def _post_start(client, *enveloppe_projets, message="Dossier incomplet", kind=REFUS):
    _post_launch(client, *enveloppe_projets, kind=kind)
    return _post_step(client, "message", {"message": message}, kind=kind)


def _content(response):
    return " ".join(response.content.decode().split())


def test_launch_keeps_only_the_projets_with_every_dotation_refused_or_dismissed(
    client, make_enveloppe_projet, perimetre, dn
):
    refused = make_enveloppe_projet(status=ProjetStatus.REFUSED)
    dismissed = make_enveloppe_projet(status=ProjetStatus.DISMISSED)
    accepted = make_enveloppe_projet(status=ProjetStatus.ACCEPTED)
    notified = make_enveloppe_projet(notified_at=timezone.now())
    refused_with_accepted_dsil = make_enveloppe_projet()
    EnveloppeProjetFactory(
        projet=refused_with_accepted_dsil.projet,
        dotation=Dotation.DSIL,
        enveloppe=DsilEnveloppeFactory(perimetre=perimetre),
        status=ProjetStatus.ACCEPTED,
    )

    response = _post_launch(
        client, refused, dismissed, accepted, notified, refused_with_accepted_dsil
    )

    assert response.status_code == 200
    content = _content(response)
    assert "2 projet(s) refusé(s) ou classé(s) sans suite" in content
    assert "3 projets de la sélection ne sont plus notifiables" in content

    _post_step(client, "message", {"message": "Hors critères"})

    job = BulkActionsJob.objects.get()
    assert job.object_ids == sorted([refused.projet_id, dismissed.projet_id])


def test_launch_without_any_eligible_projet_renders_an_error(
    client, make_enveloppe_projet
):
    accepted = make_enveloppe_projet(status=ProjetStatus.ACCEPTED)

    response = _post_launch(client, accepted)

    assert response.status_code == 200
    assert "Aucun projet à notifier." in response.content.decode()


def test_launch_skips_a_projet_whose_most_recent_campagne_is_another_one(
    client, make_enveloppe_projet, perimetre, detr_enveloppe
):
    refused = make_enveloppe_projet()
    EnveloppeProjetFactory(
        projet=refused.projet,
        dotation=Dotation.DSIL,
        enveloppe=DsilEnveloppeFactory(
            perimetre=perimetre, annee=detr_enveloppe.annee + 1
        ),
        status=ProjetStatus.REFUSED,
    )

    response = _post_launch(client, refused)

    assert "Aucun projet à notifier." in response.content.decode()


def test_start_requires_a_message(client, make_enveloppe_projet, dn):
    refused = make_enveloppe_projet()

    response = _post_start(client, refused, message="")

    assert response.status_code == 200
    assert "Ce champ est obligatoire." in response.content.decode()
    assert not BulkActionsJob.objects.exists()
    dn.refuser.assert_not_called()


def test_start_notifies_every_projet_with_the_same_message(
    client, make_enveloppe_projet, dn
):
    refused = make_enveloppe_projet(status=ProjetStatus.REFUSED)
    dismissed = make_enveloppe_projet(status=ProjetStatus.DISMISSED)

    launch_response = _post_launch(client, refused, dismissed)
    response = _post_step(client, "message", {"message": "Hors critères"})

    assert "plus notifiable" not in _content(launch_response)
    assert response.status_code == 200
    job = BulkActionsJob.objects.get(action=BulkAction.NOTIFY_REFUS)
    assert job.status == BulkActionsJob.Status.DONE
    assert job.succeeded_count == 2
    assert job.report == []
    dn.refuser.assert_called_once()
    assert dn.refuser.call_args.args[0] == refused.projet.dossier_ds
    assert dn.refuser.call_args.kwargs["motivation"] == "Hors critères"
    dn.classer_sans_suite.assert_called_once()
    assert dn.classer_sans_suite.call_args.args[0] == dismissed.projet.dossier_ds
    dn.accepter.assert_not_called()


def test_start_records_an_error_for_a_dossier_the_user_does_not_instruct(
    client, make_enveloppe_projet, dn
):
    instructed = make_enveloppe_projet()
    not_instructed = make_enveloppe_projet(instructeur=False)

    _post_start(client, instructed, not_instructed)

    job = BulkActionsJob.objects.get()
    assert job.succeeded_count == 1
    assert [error["object_id"] for error in job.report] == [not_instructed.projet_id]
    assert "pas instructeur" in job.report[0]["message"]
    dn.refuser.assert_called_once()


def test_start_goes_on_after_a_dn_error(client, make_enveloppe_projet, dn):
    failing = make_enveloppe_projet()
    succeeding = make_enveloppe_projet()

    def refuser(dossier, *args, **kwargs):
        if dossier == failing.projet.dossier_ds:
            raise DsServiceException("Dossier déjà traité")

    dn.refuser.side_effect = refuser

    _post_start(client, failing, succeeding)

    job = BulkActionsJob.objects.get()
    assert job.status == BulkActionsJob.Status.DONE
    assert job.processed == 2
    assert job.succeeded_count == 1
    assert job.report[0]["object_id"] == failing.projet_id
    assert "Dossier déjà traité" in job.report[0]["message"]


def test_task_skips_a_projet_notified_since_the_selection(
    client, make_enveloppe_projet, dn
):
    refused = make_enveloppe_projet()

    with mock.patch(
        "gsl.notification.views.bulk_notification_views.run_bulk_notification_job.delay"
    ):
        _post_start(client, refused)
    refused.projet.notified_at = timezone.now()
    refused.projet.save()
    job = BulkActionsJob.objects.get()

    run_bulk_notification_job(str(job.pk))

    job.refresh_from_db()
    assert "notifié depuis la sélection" in job.report[0]["message"]
    dn.refuser.assert_not_called()


def test_accepted_launch_keeps_only_the_projets_with_their_signed_documents(
    client, make_enveloppe_projet, dn
):
    signed = make_enveloppe_projet(status=ProjetStatus.ACCEPTED, signed=True)
    unsigned = make_enveloppe_projet(status=ProjetStatus.ACCEPTED)
    refused = make_enveloppe_projet()

    response = _post_launch(client, signed, unsigned, refused, kind=ACCEPTED)

    content = _content(response)
    assert "1 projet(s) accepté(s)." in content
    assert "2 projets de la sélection ne sont plus notifiables" in content

    _post_step(client, "message", {"message": ""}, kind=ACCEPTED)

    job = BulkActionsJob.objects.get(action=BulkAction.NOTIFY_ACCEPTED)
    assert job.object_ids == [signed.projet_id]


def test_accepted_start_notifies_without_a_message(client, make_enveloppe_projet, dn):
    signed = make_enveloppe_projet(status=ProjetStatus.ACCEPTED, signed=True)

    _post_start(client, signed, message="", kind=ACCEPTED)

    job = BulkActionsJob.objects.get()
    assert job.succeeded_count == 1
    dn.accepter.assert_called_once()
    assert dn.accepter.call_args.args[0] == signed.projet.dossier_ds
    assert dn.accepter.call_args.kwargs["motivation"] == ""
    assert dn.accepter.call_args.kwargs["document"] is mock.sentinel.merged_pdf
    dn.refuser.assert_not_called()


def test_task_skips_a_projet_whose_signed_document_was_deleted(
    client, make_enveloppe_projet, dn
):
    signed = make_enveloppe_projet(status=ProjetStatus.ACCEPTED, signed=True)

    with mock.patch(
        "gsl.notification.views.bulk_notification_views.run_bulk_notification_job.delay"
    ):
        _post_start(client, signed, message="", kind=ACCEPTED)
    UploadedDocument.objects.filter(enveloppe_projet=signed).delete()
    job = BulkActionsJob.objects.get()

    run_bulk_notification_job(str(job.pk))

    job.refresh_from_db()
    assert "documents signés" in job.report[0]["message"]
    dn.accepter.assert_not_called()


def test_progress_of_a_done_job_renders_its_report_and_tells_the_page(
    client, make_enveloppe_projet, dn
):
    refused = make_enveloppe_projet()
    _post_start(client, refused)
    job = BulkActionsJob.objects.get()

    response = client.get(
        reverse("gsl_notification:notify-progress", args=[Dotation.DETR, job.pk]),
        **HTMX_HEADERS,
    )

    content = response.content.decode()
    assert "1 projet notifié" in content
    assert "hx-trigger" not in content
    assert BulkActionsJob.DONE_EVENT in response["HX-Trigger"]


def test_progress_of_another_user_job_is_not_found(client, make_enveloppe_projet):
    job = BulkActionsJob.objects.create(
        action=BulkAction.NOTIFY_REFUS,
        created_by=CollegueWithDSProfileFactory(),
        object_ids=[],
        params={"motivation": ""},
    )

    response = client.get(
        reverse("gsl_notification:notify-progress", args=[Dotation.DETR, job.pk]),
        **HTMX_HEADERS,
    )

    assert response.status_code == 404
