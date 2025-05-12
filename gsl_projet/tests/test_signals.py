from unittest import mock

import pytest

import gsl_projet.signals as projet_signals  # noqa F401
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.signals import get_projet_status
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


def test_dont_create_projets_from_incomplete_data():
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        d = DossierFactory(ds_state=Dossier.STATE_EN_CONSTRUCTION)
        d.save()
        task_mock.assert_called_once_with(d.ds_number)
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        d = DossierFactory(ds_state="")
        d.save()
        task_mock.assert_not_called()
    with mock.patch("gsl_projet.tasks.update_projet_from_dossier.delay") as task_mock:
        dossier = DossierFactory(ds_state=Dossier.STATE_EN_INSTRUCTION)
        dossier.save()
        task_mock.assert_called_once_with(dossier.ds_number)


def test_update_projet_status_on_post_save():
    projet = ProjetFactory()
    dismissed_dotation_projet = DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_DISMISSED, dotation=DOTATION_DETR
    )

    with mock.patch("gsl_projet.models.Projet.save") as save_mock:
        dismissed_dotation_projet.save()
        save_mock.assert_called_once()
        assert projet.status == PROJET_STATUS_DISMISSED

    new_dotation_projet = DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_REFUSED, dotation=DOTATION_DSIL
    )
    with mock.patch("gsl_projet.models.Projet.save") as save_mock:
        new_dotation_projet.save()
        save_mock.assert_called_once()
        assert projet.status == PROJET_STATUS_REFUSED

    new_dotation_projet.status = PROJET_STATUS_PROCESSING
    with mock.patch("gsl_projet.models.Projet.save") as save_mock:
        new_dotation_projet.save()
        save_mock.assert_called_once()
        assert projet.status == PROJET_STATUS_PROCESSING

    new_dotation_projet.status = PROJET_STATUS_ACCEPTED
    with mock.patch("gsl_projet.models.Projet.save") as save_mock:
        new_dotation_projet.save()
        save_mock.assert_called_once()
        assert projet.status == PROJET_STATUS_ACCEPTED


def test_update_projet_status_on_post_delete():
    projet = ProjetFactory()
    accepted_dotation_projet = DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_ACCEPTED, dotation=DOTATION_DETR
    )
    refused_dotation_projet = DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_REFUSED, dotation=DOTATION_DSIL
    )

    with mock.patch("gsl_projet.models.Projet.save") as save_mock:
        accepted_dotation_projet.delete()
        save_mock.assert_called_once()
        assert projet.status is PROJET_STATUS_REFUSED

    with mock.patch("gsl_projet.models.Projet.save") as save_mock:
        refused_dotation_projet.delete()
        save_mock.assert_called_once()
        assert projet.status is None


@pytest.mark.parametrize(
    "accepted, processing, refused, dismissed, expected_status",
    (
        (True, False, False, False, PROJET_STATUS_ACCEPTED),
        (False, True, False, False, PROJET_STATUS_PROCESSING),
        (False, False, True, False, PROJET_STATUS_REFUSED),
        (False, False, False, True, PROJET_STATUS_DISMISSED),
        (True, True, False, False, PROJET_STATUS_ACCEPTED),
        (True, False, True, False, PROJET_STATUS_ACCEPTED),
        (True, False, False, True, PROJET_STATUS_ACCEPTED),
        (False, True, True, False, PROJET_STATUS_PROCESSING),
        (False, True, False, True, PROJET_STATUS_PROCESSING),
        (False, False, True, True, PROJET_STATUS_REFUSED),
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

    assert get_projet_status(projet.dotationprojet_set.first()) == expected_status
