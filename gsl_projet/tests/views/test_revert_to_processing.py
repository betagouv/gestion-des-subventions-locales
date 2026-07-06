from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

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
    dotation_projet = DotationProjetFactory(
        projet=projet,
        status=PROJET_STATUS_ACCEPTED,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        notified_at=date.today(),
    )
    return projet


@pytest.fixture
def non_notified_projet(collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=None,
    )
    DotationProjetFactory(
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


@patch("gsl_projet.forms.DsService.repasser_en_instruction")
def test_post_clears_notified_at(mock_repasser, client, notified_projet):
    assert notified_projet.notified_at is not None
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    notified_projet.refresh_from_db()
    assert notified_projet.notified_at is None


@patch("gsl_projet.forms.DsService.repasser_en_instruction")
def test_post_calls_ds_repasser_en_instruction(mock_repasser, client, notified_projet):
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    mock_repasser.assert_called_once()


@patch("gsl_projet.forms.DsService.repasser_en_instruction")
def test_post_preserves_dotation_projet_status(mock_repasser, client, notified_projet):
    dotation_projet = notified_projet.dotationprojet_set.first()
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    dotation_projet.refresh_from_db()
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED


@patch("gsl_projet.forms.DsService.repasser_en_instruction")
def test_post_preserves_programmation_projet(mock_repasser, client, notified_projet):
    dotation_projet = notified_projet.dotationprojet_set.first()
    assert hasattr(dotation_projet, "programmation_projet")
    client.post(_url(notified_projet), {}, headers={"HX-Request": "true"})
    dotation_projet.refresh_from_db()
    assert hasattr(dotation_projet, "programmation_projet")


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
    DotationProjetFactory(projet=projet, status=PROJET_STATUS_ACCEPTED)
    client = ClientWithLoggedUserFactory(other_collegue)
    response = client.get(_url(projet), headers={"HX-Request": "true"})
    assert response.status_code == 404


@patch("gsl_projet.forms.DsService.repasser_en_instruction")
def test_double_dotation_post_calls_ds_once(mock_repasser, collegue):
    projet = ProjetFactory(
        dossier_ds__perimetre=collegue.perimetre,
        notified_at=timezone.now(),
    )
    DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_ACCEPTED, dotation=DOTATION_DETR
    )
    DotationProjetFactory(
        projet=projet, status=PROJET_STATUS_ACCEPTED, dotation=DOTATION_DSIL
    )
    client = ClientWithLoggedUserFactory(collegue)
    client.post(_url(projet), {}, headers={"HX-Request": "true"})
    mock_repasser.assert_called_once()
