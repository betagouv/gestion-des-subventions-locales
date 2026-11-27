from datetime import UTC, datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from freezegun import freeze_time

from dn.sync.models import Dotation
from gsl.core.tests.factories import (
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl.historique.models import ProjetAction
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.simulation.models import SimulationProjet
from gsl.simulation.tests.factories import SimulationFactory, SimulationProjetFactory

from ...constants import ProjetStatus
from ...models import EnveloppeProjet, Projet
from ..factories import EnveloppeProjetFactory, ProjetFactory

pytestmark = pytest.mark.django_db

CAMPAGNE = 2026
CAMPAGNE_SUIVANTE = 2027
CAMPAGNE_PRECEDENTE = 2025


@pytest.fixture(autouse=True)
def campagnes(monkeypatch):
    """Three campagnes, so that the middle one can be basculed both ways."""
    campagnes = (CAMPAGNE_PRECEDENTE, CAMPAGNE, CAMPAGNE_SUIVANTE)
    monkeypatch.setattr(
        "gsl.projet.models.enveloppe_projet.CAMPAGNES", campagnes, raising=False
    )
    return campagnes


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def projet(perimetre):
    return ProjetFactory(
        dossier_ds__perimetre=perimetre, dossier_ds__finance_cout_total=100_000
    )


# -- années proposées --


@pytest.mark.parametrize(
    "annee, annees_de_bascule",
    (
        (CAMPAGNE_PRECEDENTE, [CAMPAGNE_PRECEDENTE, CAMPAGNE]),
        (CAMPAGNE, [CAMPAGNE_PRECEDENTE, CAMPAGNE, CAMPAGNE_SUIVANTE]),
        (CAMPAGNE_SUIVANTE, [CAMPAGNE, CAMPAGNE_SUIVANTE]),
    ),
)
def test_annees_de_bascule(projet, annee, annees_de_bascule):
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING, annee)

    assert ep.annees_de_bascule == annees_de_bascule


def test_annees_occupees_are_those_of_the_same_dotation(projet):
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED, CAMPAGNE_SUIVANTE)
    _enveloppe_projet(
        projet, Dotation.DSIL, ProjetStatus.PROCESSING, CAMPAGNE_PRECEDENTE
    )

    assert ep.annees_occupees == {CAMPAGNE_SUIVANTE}


def test_superseded_enveloppe_projets_dont_occupy_a_year(projet):
    ancien = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED)
    courant = EnveloppeProjet.objects.supersede(ancien)

    assert courant.annees_occupees == set()


@pytest.mark.parametrize(
    "annee, cible",
    (
        (CAMPAGNE_PRECEDENTE, CAMPAGNE_SUIVANTE),
        (CAMPAGNE_SUIVANTE, CAMPAGNE_SUIVANTE + 1),
        (CAMPAGNE, CAMPAGNE),
    ),
    ids=("non_adjacente", "absente_de_turgot", "annee_de_la_dotation"),
)
def test_can_not_basculer_to_an_unproposed_campagne(projet, annee, cible):
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING, annee)

    with pytest.raises(ValidationError):
        ep.basculer(cible)

    ep.refresh_from_db()
    assert ep.enveloppe.annee == annee


def test_can_not_basculer_onto_a_year_already_holding_the_dotation(projet):
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED, CAMPAGNE_SUIVANTE)

    with pytest.raises(ValidationError):
        ep.basculer(CAMPAGNE_SUIVANTE)

    ep.refresh_from_db()
    assert ep.enveloppe.annee == CAMPAGNE


# -- bascule --


@pytest.mark.parametrize("status", ProjetStatus.values)
@pytest.mark.parametrize("cible", (CAMPAGNE_PRECEDENTE, CAMPAGNE_SUIVANTE))
def test_basculer_changes_enveloppe_without_creating_enveloppe_projet(
    projet, status, cible
):
    ep = _enveloppe_projet(projet, Dotation.DETR, status)
    before = {
        field: getattr(ep, field)
        for field in (
            "status",
            "montant",
            "assiette",
            "date_programmation",
            "detr_avis_commission",
            "notified_at",
        )
    }

    ep.basculer(cible)

    assert EnveloppeProjet.all_objects.filter(projet=projet).count() == 1
    ep.refresh_from_db()
    assert ep.enveloppe == projet.root_enveloppe(Dotation.DETR, cible)
    assert ep.enveloppe.annee == cible
    for field, value in before.items():
        assert getattr(ep, field) == value


def test_basculer_also_moves_superseded_enveloppe_projets(projet):
    ancien = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED)
    courant = EnveloppeProjet.objects.supersede(ancien)

    courant.basculer(CAMPAGNE_SUIVANTE)

    cible = projet.root_enveloppe(Dotation.DETR, CAMPAGNE_SUIVANTE)
    ancien.refresh_from_db()
    courant.refresh_from_db()
    assert ancien.is_courant is False
    assert ancien.enveloppe == cible
    assert courant.is_courant is True
    assert courant.enveloppe == cible
    assert EnveloppeProjet.all_objects.filter(projet=projet).count() == 2


def test_basculer_only_moves_this_dotation(projet):
    detr = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.ACCEPTED)
    dsil = _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.REFUSED)

    detr.basculer(CAMPAGNE_SUIVANTE)

    detr.refresh_from_db()
    dsil.refresh_from_db()
    assert detr.enveloppe.annee == CAMPAGNE_SUIVANTE
    assert dsil.enveloppe.annee == CAMPAGNE


def test_basculer_allows_dotations_on_non_consecutive_years(projet):
    """A DSIL on the previous campagne and a DETR on the next one: no error."""
    _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.REFUSED, CAMPAGNE_PRECEDENTE)
    detr = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)

    detr.basculer(CAMPAGNE_SUIVANTE)

    detr.refresh_from_db()
    assert detr.enveloppe.annee == CAMPAGNE_SUIVANTE


def test_basculer_targets_the_root_enveloppe_for_an_arrondissement_projet():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre_arrondissement)
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    delegated = DetrEnveloppeFactory(
        perimetre=perimetre_arrondissement, annee=CAMPAGNE_SUIVANTE
    )

    ep.basculer(CAMPAGNE_SUIVANTE)

    ep.refresh_from_db()
    assert ep.enveloppe == delegated.delegation_root
    assert ep.enveloppe.is_deleguee is False
    assert ep.enveloppe.perimetre.arrondissement is None
    assert ep.enveloppe.perimetre.departement == perimetre_arrondissement.departement


def test_basculer_creates_the_root_enveloppe_when_missing_on_target_campagne(
    projet, perimetre
):
    """As `Enveloppe.objects.root_for` does for the report."""
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    origine = ep.enveloppe

    ep.basculer(CAMPAGNE_SUIVANTE)

    ep.refresh_from_db()
    assert ep.enveloppe.annee == CAMPAGNE_SUIVANTE
    assert ep.enveloppe.dotation == Dotation.DETR
    assert ep.enveloppe.perimetre == perimetre
    # Like any root enveloppe created by `root_for`: the previous year's montant
    assert ep.enveloppe.montant == origine.montant


def test_basculed_projet_leaves_origin_campagne(projet):
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.ACCEPTED)

    ep.basculer(CAMPAGNE_SUIVANTE)

    assert projet not in Projet.objects.for_campagne(CAMPAGNE)
    assert projet in Projet.objects.for_campagne(CAMPAGNE_SUIVANTE)


# -- simulations --


def test_basculer_deletes_simulation_projets_of_origin_enveloppes():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre_arrondissement)
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    delegated = DetrEnveloppeFactory(perimetre=perimetre_arrondissement, annee=CAMPAGNE)
    for enveloppe in (ep.enveloppe, delegated):
        SimulationProjetFactory(
            enveloppe_projet=ep, simulation=SimulationFactory(enveloppe=enveloppe)
        )

    ep.basculer(CAMPAGNE_SUIVANTE)

    assert not SimulationProjet.objects.filter(
        enveloppe_projet__projet=projet, simulation__enveloppe__annee=CAMPAGNE
    ).exists()


def test_basculer_creates_simulation_projets_in_target_campagne_simulations():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    departement = perimetre_arrondissement.departement
    projet = ProjetFactory(dossier_ds__perimetre=perimetre_arrondissement)
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)

    enveloppe_arrondissement = DetrEnveloppeFactory(
        perimetre=perimetre_arrondissement, annee=CAMPAGNE_SUIVANTE
    )
    simulation_departement = SimulationFactory(
        enveloppe=enveloppe_arrondissement.delegation_root
    )
    simulation_arrondissement = SimulationFactory(enveloppe=enveloppe_arrondissement)
    simulation_arrondissement_voisin = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(
            perimetre=PerimetreArrondissementFactory(
                arrondissement__departement=departement
            ),
            annee=CAMPAGNE_SUIVANTE,
        )
    )
    simulation_autre_departement = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(
            perimetre=PerimetreDepartementalFactory(), annee=CAMPAGNE_SUIVANTE
        )
    )
    simulation_dsil = SimulationFactory(
        enveloppe=DsilEnveloppeFactory(
            perimetre=perimetre_arrondissement, annee=CAMPAGNE_SUIVANTE
        ).delegation_root
    )
    simulation_campagne_precedente = SimulationFactory(
        enveloppe=DetrEnveloppeFactory(
            perimetre=perimetre_arrondissement, annee=CAMPAGNE_PRECEDENTE
        ).delegation_root
    )

    ep.basculer(CAMPAGNE_SUIVANTE)

    ep.refresh_from_db()
    simulation_projets = SimulationProjet.objects.filter(enveloppe_projet=ep)
    assert {sp.simulation for sp in simulation_projets} == {
        simulation_departement,
        simulation_arrondissement,
    }
    for simulation in (
        simulation_arrondissement_voisin,
        simulation_autre_departement,
        simulation_dsil,
        simulation_campagne_precedente,
    ):
        assert not simulation.simulationprojet_set.exists()
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert (
            simulation_projet.montant
            == SimulationProjet.objects.initial_montant_for(
                ep, SimulationProjet.STATUS_PROCESSING
            )
        )


def test_basculer_accepted_creates_valid_simulation_projet_with_montant(projet):
    ep = _enveloppe_projet(
        projet, Dotation.DETR, ProjetStatus.ACCEPTED, montant=Decimal("12345")
    )
    simulation = SimulationFactory(
        enveloppe=projet.root_enveloppe(Dotation.DETR, CAMPAGNE_SUIVANTE)
    )

    ep.basculer(CAMPAGNE_SUIVANTE)

    simulation_projet = SimulationProjet.objects.get(
        simulation=simulation, enveloppe_projet=ep
    )
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert simulation_projet.montant == Decimal("12345")


# -- pas de condition de date --


@pytest.mark.parametrize(
    "today, date_depot, date_programmation",
    (
        ("2027-01-15", None, None),
        ("2027-11-15", None, None),
        (None, "2027-01-15", None),
        (None, "2027-11-15", None),
        (None, None, "2025-12-15"),
        (None, None, "2026-11-15"),
    ),
)
@pytest.mark.parametrize("cible", (CAMPAGNE_PRECEDENTE, CAMPAGNE_SUIVANTE))
def test_basculer_does_not_depend_on_dates(
    perimetre, today, date_depot, date_programmation, cible
):
    projet = ProjetFactory(
        dossier_ds__perimetre=perimetre,
        dossier_ds__ds_date_depot=_datetime(date_depot or "2026-03-15"),
    )
    ep = _enveloppe_projet(
        projet,
        Dotation.DETR,
        ProjetStatus.REFUSED,
        date_programmation=_datetime(date_programmation or "2026-06-15"),
    )

    with freeze_time(today or "2026-10-14"):
        assert cible in ep.annees_de_bascule
        ep.basculer(cible)

    ep.refresh_from_db()
    assert ep.enveloppe.annee == cible


# -- historique --


def test_basculer_creates_a_projet_action(projet):
    user = CollegueFactory()
    ancien = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED)
    courant = EnveloppeProjet.objects.supersede(ancien)

    courant.basculer(CAMPAGNE_SUIVANTE, actor=user)

    action = ProjetAction.objects.get(
        projet=projet, action_type=ProjetAction.TYPE_BASCULE
    )
    assert action.dotation == Dotation.DETR
    assert action.actor == user
    assert action.source == ProjetAction.SOURCE_TURGOT
    assert action.enveloppe == projet.root_enveloppe(Dotation.DETR, CAMPAGNE_SUIVANTE)
    assert (
        action.action_label
        == f"Bascule DETR de la campagne {CAMPAGNE} vers {CAMPAGNE_SUIVANTE}"
    )


# -- DN --


@mock.patch("dn.sync.ds_client.DsClientBase.launch_graphql_query")
def test_basculer_does_not_call_dn(launch_graphql_query, projet):
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.ACCEPTED)

    ep.basculer(CAMPAGNE_SUIVANTE)

    launch_graphql_query.assert_not_called()


def _enveloppe_projet(projet, dotation, status, annee=CAMPAGNE, **kwargs):
    factory = (
        DetrEnveloppeFactory if dotation == Dotation.DETR else DsilEnveloppeFactory
    )
    return EnveloppeProjetFactory(
        projet=projet,
        dotation=dotation,
        status=status,
        enveloppe=factory(perimetre=projet.perimetre, annee=annee).delegation_root,
        **kwargs,
    )


def _datetime(iso_date):
    return datetime.fromisoformat(iso_date).replace(tzinfo=UTC)
