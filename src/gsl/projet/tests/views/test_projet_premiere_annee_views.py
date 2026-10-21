import re

import pytest
from django.urls import reverse

from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl.historique.models import ProjetAction
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

from ...constants import Dotation, ProjetStatus
from ...models import EnveloppeProjet
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

CAMPAGNE = 2026
CAMPAGNE_SUIVANTE = 2027


@pytest.fixture(autouse=True)
def campagnes(monkeypatch):
    campagnes = (CAMPAGNE, CAMPAGNE_SUIVANTE)
    monkeypatch.setattr("gsl.core.campagne.CAMPAGNES", campagnes)
    monkeypatch.setattr("gsl.projet.models.projet.CAMPAGNES", campagnes)
    return campagnes


@pytest.fixture
def collegue():
    return CollegueWithDSProfileFactory(perimetre=PerimetreDepartementalFactory())


@pytest.fixture
def client(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def projet(collegue):
    projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
    _enveloppe_projet(projet, Dotation.DETR, CAMPAGNE)
    return projet


# -- affichage sur la fiche projet --


def test_selecteur_is_displayed_with_the_projet_campagne_checked(client, projet):
    response = client.get(_detail_url(projet))

    assert response.status_code == 200
    content = response.content.decode()
    assert _url(projet) in content
    assert "Première année de traitement" in content
    assert _checked_radio(content) == str(CAMPAGNE)
    assert f'value="{CAMPAGNE_SUIVANTE}"' in content


def test_selecteur_is_hidden_for_a_projet_on_two_campagnes(client, projet):
    _enveloppe_projet(projet, Dotation.DSIL, CAMPAGNE_SUIVANTE)

    response = client.get(_detail_url(projet))

    assert response.status_code == 200
    assert _url(projet) not in response.content.decode()


# -- enregistrement --


def test_post_another_campagne_basculer_the_projet_and_refreshes_the_page(
    client, collegue, projet
):
    response = client.post(
        _url(projet), {"campagne": CAMPAGNE_SUIVANTE}, headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert response.headers["HX-Refresh"] == "true"
    ep = EnveloppeProjet.objects.get(projet=projet)
    assert ep.enveloppe.annee == CAMPAGNE_SUIVANTE
    action = ProjetAction.objects.get(
        projet=projet, action_type=ProjetAction.TYPE_BASCULE
    )
    assert action.actor == collegue

    page = client.get(_detail_url(projet)).content.decode()
    assert f"Le projet a été basculé sur la campagne {CAMPAGNE_SUIVANTE}." in page


def test_post_the_same_campagne_does_nothing(client, projet):
    response = client.post(
        _url(projet), {"campagne": CAMPAGNE}, headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    ep = EnveloppeProjet.objects.get(projet=projet)
    assert ep.enveloppe.annee == CAMPAGNE
    assert not ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_BASCULE
    ).exists()
    assert "basculé" not in client.get(_detail_url(projet)).content.decode()


def test_post_an_unproposed_campagne_shows_an_error(client, projet):
    response = client.post(
        _url(projet), {"campagne": 2030}, headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert "HX-Refresh" not in response.headers
    assert "Sélectionnez un choix valide" in response.content.decode()
    ep = EnveloppeProjet.objects.get(projet=projet)
    assert ep.enveloppe.annee == CAMPAGNE


def test_post_out_of_perimetre_returns_404(client):
    other_projet = ProjetFactory(dossier_ds__perimetre=PerimetreDepartementalFactory())
    _enveloppe_projet(other_projet, Dotation.DETR, CAMPAGNE)

    response = client.post(
        _url(other_projet),
        {"campagne": CAMPAGNE_SUIVANTE},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 404
    ep = EnveloppeProjet.objects.get(projet=other_projet)
    assert ep.enveloppe.annee == CAMPAGNE


def test_post_non_htmx_returns_400(client, projet):
    response = client.post(_url(projet), {"campagne": CAMPAGNE_SUIVANTE})

    assert response.status_code == 400
    ep = EnveloppeProjet.objects.get(projet=projet)
    assert ep.enveloppe.annee == CAMPAGNE


def _url(projet):
    return reverse("fragment:gsl_projet:premiere_annee_form", kwargs={"pk": projet.pk})


def _detail_url(projet):
    return reverse("gsl_projet:get-projet", kwargs={"projet_id": projet.pk})


def _checked_radio(content):
    """Value of the checked radio of the campagne field."""
    match = re.search(r'name="campagne"[^>]*value="(\d+)"[^>]*checked', content)
    if match is None:
        match = re.search(r'name="campagne"[^>]*checked[^>]*value="(\d+)"', content)
    return match.group(1) if match else None


def _enveloppe_projet(projet, dotation, annee):
    factory = (
        DetrEnveloppeFactory if dotation == Dotation.DETR else DsilEnveloppeFactory
    )
    return EnveloppeProjetFactory(
        projet=projet,
        dotation=dotation,
        status=ProjetStatus.PROCESSING,
        enveloppe=factory(perimetre=projet.perimetre, annee=annee).delegation_root,
    )
