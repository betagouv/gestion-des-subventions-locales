from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from gsl.core.tests.factories import CollegueFactory, PerimetreDepartementalFactory
from gsl.programmation.tests.factories import DetrEnveloppeFactory
from gsl.projet.constants import DOTATION_DETR, ProjetStatus
from gsl.projet.templatetags.enveloppe_tags import enveloppe_summary_line
from gsl.projet.tests.factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

CAMPAGNE = 2026
CAMPAGNE_SUIVANTE = 2027


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def client(perimetre):
    client = Client()
    client.force_login(CollegueFactory(perimetre=perimetre))
    return client


@pytest.fixture
def enveloppe(perimetre):
    return DetrEnveloppeFactory(perimetre=perimetre, annee=CAMPAGNE, montant=500_000)


@pytest.fixture
def enveloppe_suivante(perimetre):
    return DetrEnveloppeFactory(
        perimetre=perimetre, annee=CAMPAGNE_SUIVANTE, montant=500_000
    )


@pytest.fixture
def enveloppe_projet(perimetre, enveloppe):
    return EnveloppeProjetFactory(
        projet=ProjetFactory(
            dossier_ds__perimetre=perimetre, dossier_ds__finance_cout_total=100_000
        ),
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        montant=Decimal("20000"),
        enveloppe=enveloppe,
    )


def test_basculed_projet_leaves_origin_programmation_list(
    client, enveloppe_projet, enveloppe_suivante
):
    enveloppe_projet.projet.basculer(CAMPAGNE_SUIVANTE)

    origine = client.get(_programmation_url(CAMPAGNE))
    cible = client.get(_programmation_url(CAMPAGNE_SUIVANTE))

    assert origine.status_code == 200
    assert enveloppe_projet not in origine.context["enveloppe_projets"]
    assert cible.status_code == 200
    assert enveloppe_projet in cible.context["enveloppe_projets"]


def test_basculed_accepted_montant_moves_between_enveloppe_recaps(
    enveloppe, enveloppe_suivante, enveloppe_projet
):
    assert _summary(enveloppe)["accepted_montant"] == Decimal("20000")
    assert _summary(enveloppe_suivante)["accepted_montant"] == 0

    enveloppe_projet.projet.basculer(CAMPAGNE_SUIVANTE)

    origine = _summary(enveloppe)
    assert origine["accepted_montant"] == 0
    assert origine["validated_projets_count"] == 0
    assert origine["projets_count"] == 0
    assert origine["reste_a_attribuer"] == enveloppe.montant
    cible = _summary(enveloppe_suivante)
    assert cible["accepted_montant"] == Decimal("20000")
    assert cible["validated_projets_count"] == 1
    assert cible["projets_count"] == 1
    assert cible["reste_a_attribuer"] == enveloppe_suivante.montant - Decimal("20000")


def _programmation_url(campagne):
    return reverse(
        "gsl_programmation:programmation-projet-list-dotation",
        kwargs={"dotation": DOTATION_DETR, "campagne": campagne},
    )


def _summary(enveloppe):
    return enveloppe_summary_line({}, enveloppe)
