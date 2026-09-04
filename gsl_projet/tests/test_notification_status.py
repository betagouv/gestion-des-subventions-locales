from datetime import UTC, datetime

import pytest

from gsl_notification.tests.factories import (
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    LettreRefusFactory,
    LettreRefusSigneeFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    NOTIFICATION_STATUS_NOTIFIED,
    NOTIFICATION_STATUS_TO_GENERATE,
    NOTIFICATION_STATUS_TO_NOTIFY,
    NOTIFICATION_STATUS_TO_SIGN,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import DotationProjetFactory

pytestmark = pytest.mark.django_db


def _assert_property_matches_annotation(dotation_projet: DotationProjet):
    """
    Checks all three access paths agree: the property's fallback computation
    (non-annotated instance), the raw queryset annotation, and the property's
    fast path when called on an already-annotated instance.
    """
    annotated_instance = DotationProjet.objects.annotate_notification_status().get(
        pk=dotation_projet.pk
    )

    assert (
        dotation_projet.notification_status == annotated_instance._notification_status
    )
    assert dotation_projet.notification_status == annotated_instance.notification_status


def test_dotation_projet_without_programmation_has_no_notification_status():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_PROCESSING)

    assert dotation_projet.notification_status is None
    _assert_property_matches_annotation(dotation_projet)


def test_dotation_projet_with_programmation_but_no_document_is_to_generate():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    ProgrammationProjetFactory(dotation_projet=dotation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    _assert_property_matches_annotation(dotation_projet)


def test_accepted_dotation_projet_with_both_documents_is_to_sign():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    ArreteFactory(programmation_projet=programmation_projet)
    LettreNotificationFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_SIGN
    _assert_property_matches_annotation(dotation_projet)


def test_accepted_dotation_projet_with_only_one_document_is_to_generate():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    ArreteFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    _assert_property_matches_annotation(dotation_projet)


def test_dotation_projet_with_signed_documents_is_to_notify():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    LettreEtArreteSignesFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_NOTIFY
    _assert_property_matches_annotation(dotation_projet)


def test_notified_projet_dotation_is_notified_even_with_no_signed_document():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_ACCEPTED)
    ProgrammationProjetFactory(dotation_projet=dotation_projet)
    dotation_projet.projet.notified_at = datetime.now(UTC)
    dotation_projet.projet.save()

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_NOTIFIED
    _assert_property_matches_annotation(dotation_projet)


@pytest.mark.parametrize("status", [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED])
def test_refused_or_dismissed_dotation_projet_with_programmation_is_to_generate(status):
    dotation_projet = DotationProjetFactory(status=status)
    ProgrammationProjetFactory(dotation_projet=dotation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    _assert_property_matches_annotation(dotation_projet)


@pytest.mark.parametrize("status", [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED])
def test_refused_or_dismissed_dotation_projet_with_lettre_refus_is_to_sign(status):
    dotation_projet = DotationProjetFactory(status=status)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    LettreRefusFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_SIGN
    _assert_property_matches_annotation(dotation_projet)


@pytest.mark.parametrize("status", [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED])
def test_refused_or_dismissed_dotation_projet_with_signed_lettre_refus_is_to_notify(
    status,
):
    dotation_projet = DotationProjetFactory(status=status)
    programmation_projet = ProgrammationProjetFactory(dotation_projet=dotation_projet)
    LettreRefusSigneeFactory(programmation_projet=programmation_projet)

    assert dotation_projet.notification_status == NOTIFICATION_STATUS_TO_NOTIFY
    _assert_property_matches_annotation(dotation_projet)
