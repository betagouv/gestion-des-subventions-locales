from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)

from ...constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
)
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db


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
def notified_projet(collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=PROJET_STATUS_ACCEPTED,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    return projet


@pytest.fixture
def non_notified_projet(collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=None,
    )
    EnveloppeProjetFactory(
        projet=projet,
        status=PROJET_STATUS_ACCEPTED,
        dotation=DOTATION_DETR,
    )
    return projet


def _url(projet):
    return reverse("gsl_projet:revert-to-processing", kwargs={"projet_id": projet.id})


def test_get_modal_returns_confirmation(client, notified_projet):
    response = client.get(_url(notified_projet), headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Repasser le projet en traitement" in response.content.decode()


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_post_clears_notified_at(mock_repasser, client, notified_projet):
    assert notified_projet.notified_at is not None
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    notified_projet.refresh_from_db()
    assert notified_projet.notified_at is None


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_post_calls_ds_repasser_en_instruction(mock_repasser, client, notified_projet):
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    mock_repasser.assert_called_once()


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_post_preserves_enveloppe_projet_status(mock_repasser, client, notified_projet):
    enveloppe_projet = notified_projet.enveloppeprojet_set.first()
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.status == PROJET_STATUS_ACCEPTED


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_post_preserves_programmation(mock_repasser, client, notified_projet):
    enveloppe_projet = notified_projet.enveloppeprojet_set.first()
    assert enveloppe_projet.is_programmee
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.is_programmee


def test_get_returns_404_for_non_notified_projet(client, non_notified_projet):
    response = client.get(_url(non_notified_projet), headers={"HX-Request": "true"})
    assert response.status_code == 404


def test_get_returns_404_for_out_of_perimeter_projet():
    other_perimetre = PerimetreDepartementalFactory()
    other_collegue = CollegueWithDSProfileFactory(perimetre=other_perimetre)
    projet = ProjetFactory(
        dossier_ds__perimetre=PerimetreDepartementalFactory(),
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(projet=projet, status=PROJET_STATUS_ACCEPTED)
    client = ClientWithLoggedUserFactory(other_collegue)
    response = client.get(_url(projet), headers={"HX-Request": "true"})
    assert response.status_code == 404


@patch("gsl.projet.forms.DsService.repasser_en_instruction")
def test_double_dotation_post_calls_ds_once(mock_repasser, collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=timezone.now(),
    )
    EnveloppeProjetFactory(
        projet=projet, status=PROJET_STATUS_ACCEPTED, dotation=DOTATION_DETR
    )
    EnveloppeProjetFactory(
        projet=projet, status=PROJET_STATUS_ACCEPTED, dotation=DOTATION_DSIL
    )
    client = ClientWithLoggedUserFactory(collegue)
    client.post(_url(projet), {}, headers={"HX-Request": "true"})
    mock_repasser.assert_called_once()
