from datetime import UTC, datetime

import pytest

from gsl.notification.tests.factories import (
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    LettreRefusFactory,
    LettreRefusSigneeFactory,
)

from ..constants import (
    NOTIFICATION_STATUS_NOTIFIED,
    NOTIFICATION_STATUS_TO_GENERATE,
    NOTIFICATION_STATUS_TO_NOTIFY,
    NOTIFICATION_STATUS_TO_SIGN,
    ProjetStatus,
)
from ..models import EnveloppeProjet
from .factories import EnveloppeProjetFactory

pytestmark = pytest.mark.django_db


def _assert_property_matches_annotation(enveloppe_projet: EnveloppeProjet):
    """
    Checks all three access paths agree: the property's fallback computation
    (non-annotated instance), the raw queryset annotation, and the property's
    fast path when called on an already-annotated instance.
    """
    annotated_instance = EnveloppeProjet.objects.annotate_notification_status().get(
        pk=enveloppe_projet.pk
    )

    assert (
        enveloppe_projet.notification_status == annotated_instance._notification_status
    )
    assert (
        enveloppe_projet.notification_status == annotated_instance.notification_status
    )


def test_enveloppe_projet_without_programmation_has_no_notification_status():
    enveloppe_projet = EnveloppeProjetFactory(status=ProjetStatus.PROCESSING)

    assert enveloppe_projet.notification_status is None
    _assert_property_matches_annotation(enveloppe_projet)


def test_enveloppe_projet_with_programmation_but_no_document_is_to_generate():
    enveloppe_projet = EnveloppeProjetFactory(status=ProjetStatus.ACCEPTED)

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    _assert_property_matches_annotation(enveloppe_projet)


def test_accepted_enveloppe_projet_with_both_documents_is_to_sign():
    enveloppe_projet = EnveloppeProjetFactory(status=ProjetStatus.ACCEPTED)
    ArreteFactory(enveloppe_projet=enveloppe_projet)
    LettreNotificationFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_TO_SIGN
    _assert_property_matches_annotation(enveloppe_projet)


def test_accepted_enveloppe_projet_with_only_one_document_is_to_generate():
    enveloppe_projet = EnveloppeProjetFactory(status=ProjetStatus.ACCEPTED)
    ArreteFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    _assert_property_matches_annotation(enveloppe_projet)


def test_enveloppe_projet_with_signed_documents_is_to_notify():
    enveloppe_projet = EnveloppeProjetFactory(status=ProjetStatus.ACCEPTED)
    LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_TO_NOTIFY
    _assert_property_matches_annotation(enveloppe_projet)


def test_notified_projet_dotation_is_notified_even_with_no_signed_document():
    enveloppe_projet = EnveloppeProjetFactory(status=ProjetStatus.ACCEPTED)
    enveloppe_projet.projet.notified_at = datetime.now(UTC)
    enveloppe_projet.projet.save()

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_NOTIFIED
    _assert_property_matches_annotation(enveloppe_projet)


@pytest.mark.parametrize("status", [ProjetStatus.REFUSED, ProjetStatus.DISMISSED])
def test_refused_or_dismissed_enveloppe_projet_with_programmation_is_to_generate(
    status,
):
    enveloppe_projet = EnveloppeProjetFactory(status=status)

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_TO_GENERATE
    _assert_property_matches_annotation(enveloppe_projet)


@pytest.mark.parametrize("status", [ProjetStatus.REFUSED, ProjetStatus.DISMISSED])
def test_refused_or_dismissed_enveloppe_projet_with_lettre_refus_is_to_sign(status):
    enveloppe_projet = EnveloppeProjetFactory(status=status)
    LettreRefusFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_TO_SIGN
    _assert_property_matches_annotation(enveloppe_projet)


@pytest.mark.parametrize("status", [ProjetStatus.REFUSED, ProjetStatus.DISMISSED])
def test_refused_or_dismissed_enveloppe_projet_with_signed_lettre_refus_is_to_notify(
    status,
):
    enveloppe_projet = EnveloppeProjetFactory(status=status)
    LettreRefusSigneeFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.notification_status == NOTIFICATION_STATUS_TO_NOTIFY
    _assert_property_matches_annotation(enveloppe_projet)
