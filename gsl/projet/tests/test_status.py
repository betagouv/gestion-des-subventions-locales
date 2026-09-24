import pytest

from gsl_programmation.tests.factories import DetrEnveloppeFactory

from ..constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ..models import EnveloppeProjet, Projet
from .factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


def test_projet_without_enveloppe_projet_has_no_status():
    projet = ProjetFactory()
    assert projet.status is None


def test_update_projet_status_on_post_save():
    projet: Projet = ProjetFactory()
    enveloppe = DetrEnveloppeFactory()
    enveloppe_projet: EnveloppeProjet = EnveloppeProjetFactory(
        projet=projet,
        status=ProjetStatus.DISMISSED,
        dotation=DOTATION_DETR,
        enveloppe=enveloppe,
    )

    enveloppe_projet.save()
    assert projet.status == ProjetStatus.DISMISSED

    enveloppe_projet.refuse(enveloppe=enveloppe)
    enveloppe_projet.save()
    assert projet.status == ProjetStatus.REFUSED

    enveloppe_projet.set_back_status_to_processing_without_ds()
    enveloppe_projet.save()
    assert projet.status == ProjetStatus.PROCESSING

    enveloppe_projet.accept_without_ds_update(montant=1_000, enveloppe=enveloppe)
    enveloppe_projet.save()
    assert projet.status == ProjetStatus.ACCEPTED


def test_update_projet_status_on_post_delete():
    projet = ProjetFactory()
    accepted_enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.ACCEPTED, dotation=DOTATION_DETR
    )
    EnveloppeProjetFactory(
        projet=projet, status=ProjetStatus.REFUSED, dotation=DOTATION_DSIL
    )

    accepted_enveloppe_projet.delete()
    assert projet.status is ProjetStatus.REFUSED


@pytest.mark.parametrize(
    "accepted, processing, refused, dismissed, expected_status",
    (
        (True, False, False, False, ProjetStatus.ACCEPTED),
        (False, True, False, False, ProjetStatus.PROCESSING),
        (False, False, True, False, ProjetStatus.REFUSED),
        (False, False, False, True, ProjetStatus.DISMISSED),
        (True, True, False, False, ProjetStatus.PROCESSING),
        (True, False, True, False, ProjetStatus.ACCEPTED),
        (True, False, False, True, ProjetStatus.ACCEPTED),
        (False, True, True, False, ProjetStatus.PROCESSING),
        (False, True, False, True, ProjetStatus.PROCESSING),
        (False, False, True, True, ProjetStatus.DISMISSED),
    ),
)
def test_status_mixed_dotations(
    accepted, processing, refused, dismissed, expected_status
):
    projet = ProjetFactory()
    current_dotation = DOTATION_DETR

    if accepted:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.ACCEPTED,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if processing:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.PROCESSING,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if refused:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.REFUSED,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if dismissed:
        EnveloppeProjetFactory(
            projet=projet,
            status=ProjetStatus.DISMISSED,
            dotation=current_dotation,
        )

    assert projet.status == expected_status
