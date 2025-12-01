import pytest

from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


def test_update_projet_status_on_post_save():
    projet: Projet = ProjetFactory()
    dotation_projet: DotationProjet = DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_DISMISSED, dotation=DOTATION_DETR
    )

    dotation_projet.save()
    assert projet.status == PROJET_STATUS_DISMISSED

    dotation_projet.status = PROJET_STATUS_REFUSED
    dotation_projet.save()
    assert projet.status == PROJET_STATUS_REFUSED

    dotation_projet.status = PROJET_STATUS_PROCESSING
    dotation_projet.save()
    assert projet.status == PROJET_STATUS_PROCESSING

    dotation_projet.status = PROJET_STATUS_ACCEPTED
    dotation_projet.save()
    assert projet.status == PROJET_STATUS_ACCEPTED


def test_update_projet_status_on_post_delete():
    projet = ProjetFactory()
    accepted_dotation_projet = DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_ACCEPTED, dotation=DOTATION_DETR
    )
    DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_REFUSED, dotation=DOTATION_DSIL
    )

    accepted_dotation_projet.delete()
    assert projet.status is PROJET_STATUS_REFUSED


@pytest.mark.parametrize(
    "accepted, processing, refused, dismissed, expected_status",
    (
        (True, False, False, False, PROJET_STATUS_ACCEPTED),
        (False, True, False, False, PROJET_STATUS_PROCESSING),
        (False, False, True, False, PROJET_STATUS_REFUSED),
        (False, False, False, True, PROJET_STATUS_DISMISSED),
        (True, True, False, False, PROJET_STATUS_PROCESSING),
        (True, False, True, False, PROJET_STATUS_ACCEPTED),
        (True, False, False, True, PROJET_STATUS_ACCEPTED),
        (False, True, True, False, PROJET_STATUS_PROCESSING),
        (False, True, False, True, PROJET_STATUS_PROCESSING),
        (False, False, True, True, PROJET_STATUS_DISMISSED),
    ),
)
def test_status_mixed_dotations(
    accepted, processing, refused, dismissed, expected_status
):
    projet = ProjetFactory()
    current_dotation = DOTATION_DETR

    if accepted:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_ACCEPTED,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if processing:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_PROCESSING,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if refused:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_REFUSED,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if dismissed:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_DISMISSED,
            dotation=current_dotation,
        )

    assert projet.status == expected_status
