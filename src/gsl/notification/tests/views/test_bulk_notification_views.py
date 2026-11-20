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
from gsl.notification.tasks import run_bulk_notification_refus_job
from gsl.programmation.constants import BulkAction
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.projet.constants import ProjetStatus
from gsl.projet.tests.factories import EnveloppeProjetFactory

pytestmark = pytest.mark.django_db

HTMX_HEADERS = {"HTTP_HX_REQUEST": "true"}
WIZARD_PREFIX = f"notify_refus_wizard_{Dotation.DETR}"


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
    def make(status=ProjetStatus.REFUSED, instructeur=True, notified_at=None, **kwargs):
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
        return enveloppe_projet

    return make


@pytest.fixture
def dn():
    with (
        mock.patch("dn.sync.services.DsService.passer_en_instruction"),
        mock.patch("dn.sync.services.DsService.refuser") as refuser,
        mock.patch("dn.sync.services.DsService.classer_sans_suite") as dismiss,
        mock.patch("dn.sync.services.DsService.accepter") as accepter,
    ):
        yield mock.Mock(refuser=refuser, classer_sans_suite=dismiss, accepter=accepter)


def _post_step(client, step, fields):
    data = {f"{WIZARD_PREFIX}-current_step": step}
    data.update({f"{step}-{key}": value for key, value in fields.items()})
    return client.post(
        reverse("gsl_notification:notify-refus-modal", args=[Dotation.DETR]),
        data,
        **HTMX_HEADERS,
    )


def _post_launch(client, *enveloppe_projets):
    ids = ",".join(str(enveloppe_projet.pk) for enveloppe_projet in enveloppe_projets)
    return _post_step(client, "launch", {"ids": ids})


def _post_start(client, *enveloppe_projets, message="Dossier incomplet"):
    _post_launch(client, *enveloppe_projets)
    return _post_step(client, "message", {"message": message})


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
    content = " ".join(response.content.decode().split())
    assert "2 projets refusés ou classés sans suite" in content

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

    response = _post_start(client, refused, dismissed, message="Hors critères")

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
        "gsl.notification.views.bulk_notification_views.run_bulk_notification_refus_job.delay"
    ):
        _post_start(client, refused)
    refused.projet.notified_at = timezone.now()
    refused.projet.save()
    job = BulkActionsJob.objects.get()

    run_bulk_notification_refus_job(str(job.pk))

    job.refresh_from_db()
    assert "notifié depuis la sélection" in job.report[0]["message"]
    dn.refuser.assert_not_called()


def test_progress_of_a_done_job_renders_its_report_and_stops_polling(
    client, make_enveloppe_projet, dn
):
    refused = make_enveloppe_projet()
    _post_start(client, refused)
    job = BulkActionsJob.objects.get()

    response = client.get(
        reverse("gsl_notification:notify-refus-progress", args=[Dotation.DETR, job.pk]),
        **HTMX_HEADERS,
    )

    content = response.content.decode()
    assert "1 projet notifié" in content
    assert "hx-trigger" not in content


def test_progress_of_another_user_job_is_not_found(client, make_enveloppe_projet):
    job = BulkActionsJob.objects.create(
        action=BulkAction.NOTIFY_REFUS,
        created_by=CollegueWithDSProfileFactory(),
        object_ids=[],
        params={"motivation": ""},
    )

    response = client.get(
        reverse("gsl_notification:notify-refus-progress", args=[Dotation.DETR, job.pk]),
        **HTMX_HEADERS,
    )

    assert response.status_code == 404
