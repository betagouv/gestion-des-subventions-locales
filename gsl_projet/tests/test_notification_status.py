from datetime import UTC, datetime

import pytest

from gsl_notification.tests.factories import (
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    NOTIFICATION_STATUS_NOTIFIED,
    NOTIFICATION_STATUS_TO_GENERATE,
    NOTIFICATION_STATUS_TO_NOTIFY,
    NOTIFICATION_STATUS_TO_SIGN,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import DotationProjetFactory

pytestmark = pytest.mark.django_db


def _annotated_status(dotation_projet: DotationProjet):
    return (
        DotationProjet.objects.annotate_notification_status()
        .get(pk=dotation_projet.pk)
        ._notification_status
    )


def test_dotation_projet_without_programmation_has_no_notification_status():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_PROCESSING)

    assert dotation_projet.notification_status is None
    assert _annotated_status(dotation_projet) is None


def test_dotation_projet_with_programmation_but_no_document_is_to_generate():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    ProgrammationProjetFactory(dotation_projet=dotation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    assert _annotated_status(dotation_projet) == NOTIFICATION_STATUS_TO_GENERATE


def test_accepted_dotation_projet_with_both_documents_is_to_sign():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    ArreteFactory(programmation_projet=programmation_projet)
    LettreNotificationFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_SIGN
    assert _annotated_status(dotation_projet) == NOTIFICATION_STATUS_TO_SIGN


def test_accepted_dotation_projet_with_only_one_document_is_to_generate():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    ArreteFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    assert _annotated_status(dotation_projet) == NOTIFICATION_STATUS_TO_GENERATE


def test_dotation_projet_with_signed_documents_is_to_notify():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    LettreEtArreteSignesFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_NOTIFY
    assert _annotated_status(dotation_projet) == NOTIFICATION_STATUS_TO_NOTIFY


def test_notified_projet_dotation_is_notified_even_with_no_signed_document():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    ProgrammationProjetFactory(dotation_projet=dotation_projet)
    dotation_projet.projet.notified_at = datetime.now(UTC)
    dotation_projet.projet.save()

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_NOTIFIED
    assert _annotated_status(dotation_projet) == NOTIFICATION_STATUS_NOTIFIED
