from datetime import UTC, datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from freezegun import freeze_time

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

from ...constants import Dotation, ProjetStatus
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
    monkeypatch.setattr("gsl.core.campagne.CAMPAGNES", campagnes)
    monkeypatch.setattr("gsl.projet.models.projet.CAMPAGNES", campagnes, raising=False)
    return campagnes


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def projet(perimetre):
    return ProjetFactory(
        dossier_ds__perimetre=perimetre, dossier_ds__finance_cout_total=100_000
    )


# -- campagne du projet --


def test_campagne_is_the_one_of_its_enveloppe_projets(projet):
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.ACCEPTED)

    assert projet.campagne == CAMPAGNE


def test_campagne_is_none_for_a_projet_on_two_campagnes(projet):
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED, CAMPAGNE)
    _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.PROCESSING, CAMPAGNE_SUIVANTE)

    assert projet.campagne is None


def test_campagne_is_none_without_enveloppe_projet(projet):
    assert projet.campagne is None


# -- campagnes proposées --


@pytest.mark.parametrize(
    "annee, campagnes_de_bascule",
    (
        (CAMPAGNE, [CAMPAGNE_PRECEDENTE, CAMPAGNE_SUIVANTE]),
        (CAMPAGNE_SUIVANTE, [CAMPAGNE]),
        (CAMPAGNE_PRECEDENTE, [CAMPAGNE]),
    ),
)
def test_campagnes_de_bascule(projet, annee, campagnes_de_bascule):
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING, annee)

    assert projet.campagnes_de_bascule == campagnes_de_bascule


@pytest.mark.parametrize(
    "annee, cible",
    (
        (CAMPAGNE_PRECEDENTE, CAMPAGNE_SUIVANTE),
        (CAMPAGNE_SUIVANTE, CAMPAGNE_SUIVANTE + 1),
        (CAMPAGNE, CAMPAGNE),
    ),
    ids=("non_adjacente", "absente_de_turgot", "campagne_du_projet"),
)
def test_can_not_basculer_to_an_unproposed_campagne(projet, annee, cible):
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING, annee)

    with pytest.raises(ValidationError):
        projet.basculer(cible)

    ep.refresh_from_db()
    assert ep.enveloppe.annee == annee


# -- cas simple dotation --


@pytest.mark.parametrize("status", ProjetStatus.values)
@pytest.mark.parametrize("cible", (CAMPAGNE_PRECEDENTE, CAMPAGNE_SUIVANTE))
def test_basculer_single_dotation_changes_enveloppe_without_creating_enveloppe_projet(
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
        )
    }

    projet.basculer(cible)

    assert EnveloppeProjet.all_objects.filter(projet=projet).count() == 1
    ep.refresh_from_db()
    assert ep.enveloppe == projet.root_enveloppe(Dotation.DETR, cible)
    assert ep.enveloppe.annee == cible
    for field, value in before.items():
        assert getattr(ep, field) == value


def test_basculer_also_moves_superseded_enveloppe_projets(projet):
    ancien = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED)
    courant = EnveloppeProjet.objects.supersede(ancien)

    projet.basculer(CAMPAGNE_SUIVANTE)

    cible = projet.root_enveloppe(Dotation.DETR, CAMPAGNE_SUIVANTE)
    ancien.refresh_from_db()
    courant.refresh_from_db()
    assert ancien.is_courant is False
    assert ancien.enveloppe == cible
    assert courant.is_courant is True
    assert courant.enveloppe == cible
    assert EnveloppeProjet.all_objects.filter(projet=projet).count() == 2


def test_superseded_enveloppe_projets_dont_make_a_second_campagne(projet):
    ancien = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED)
    _nouveau = EnveloppeProjet.objects.supersede(ancien)

    assert projet.campagnes_de_bascule == [CAMPAGNE_PRECEDENTE, CAMPAGNE_SUIVANTE]


def test_basculer_targets_the_root_enveloppe_for_an_arrondissement_projet():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    projet = ProjetFactory(dossier_ds__perimetre=perimetre_arrondissement)
    ep = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    delegated = DetrEnveloppeFactory(
        perimetre=perimetre_arrondissement, annee=CAMPAGNE_SUIVANTE
    )

    projet.basculer(CAMPAGNE_SUIVANTE)

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

    projet.basculer(CAMPAGNE_SUIVANTE)

    ep.refresh_from_db()
    assert ep.enveloppe.annee == CAMPAGNE_SUIVANTE
    assert ep.enveloppe.dotation == Dotation.DETR
    assert ep.enveloppe.perimetre == perimetre
    # Like any root enveloppe created by `root_for`: the previous year's montant
    assert ep.enveloppe.montant == origine.montant


# -- cas double dotation --


@pytest.mark.parametrize(
    "status_detr, status_dsil",
    (
        (ProjetStatus.ACCEPTED, ProjetStatus.ACCEPTED),
        (ProjetStatus.ACCEPTED, ProjetStatus.REFUSED),
        (ProjetStatus.ACCEPTED, ProjetStatus.DISMISSED),
        (ProjetStatus.REFUSED, ProjetStatus.DISMISSED),
        (ProjetStatus.PROCESSING, ProjetStatus.PROCESSING),
        (ProjetStatus.PROCESSING, ProjetStatus.ACCEPTED),
        (ProjetStatus.PROCESSING, ProjetStatus.REFUSED),
    ),
)
def test_basculer_double_dotation_moves_both(projet, status_detr, status_dsil):
    detr = _enveloppe_projet(projet, Dotation.DETR, status_detr)
    dsil = _enveloppe_projet(projet, Dotation.DSIL, status_dsil)

    projet.basculer(CAMPAGNE_SUIVANTE)

    detr.refresh_from_db()
    dsil.refresh_from_db()
    assert detr.enveloppe == projet.root_enveloppe(Dotation.DETR, CAMPAGNE_SUIVANTE)
    assert dsil.enveloppe == projet.root_enveloppe(Dotation.DSIL, CAMPAGNE_SUIVANTE)
    assert detr.status == status_detr
    assert dsil.status == status_dsil
    assert EnveloppeProjet.all_objects.filter(projet=projet).count() == 2


# -- une seule campagne --


def test_can_not_basculer_a_projet_on_two_campagnes(projet):
    """Typically a reported projet, or a dotation added on another campagne."""
    detr = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED, CAMPAGNE)
    dsil = _enveloppe_projet(
        projet, Dotation.DSIL, ProjetStatus.PROCESSING, CAMPAGNE_SUIVANTE
    )

    assert projet.campagnes_de_bascule == []
    for cible in (CAMPAGNE_PRECEDENTE, CAMPAGNE, CAMPAGNE_SUIVANTE):
        with pytest.raises(ValidationError):
            projet.basculer(cible)

    detr.refresh_from_db()
    dsil.refresh_from_db()
    assert detr.enveloppe.annee == CAMPAGNE
    assert dsil.enveloppe.annee == CAMPAGNE_SUIVANTE


@pytest.mark.skip(reason="Dépend du merge du report (ma/report-projet)")
def test_can_not_basculer_a_reported_projet(projet):
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED)
    projet.reporter_without_dn()

    assert projet.campagnes_de_bascule == []
    with pytest.raises(ValidationError):
        projet.basculer(CAMPAGNE_SUIVANTE)


# -- le projet ne compte plus dans la campagne d'origine --


def test_basculed_projet_leaves_origin_campagne(projet):
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.ACCEPTED)
    _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.REFUSED)

    projet.basculer(CAMPAGNE_SUIVANTE)

    assert projet not in Projet.objects.for_campagne(CAMPAGNE)
    assert projet in Projet.objects.for_campagne(CAMPAGNE_SUIVANTE)
    assert not EnveloppeProjet.all_objects.filter(
        projet=projet, enveloppe__annee=CAMPAGNE
    ).exists()


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

    projet.basculer(CAMPAGNE_SUIVANTE)

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

    projet.basculer(CAMPAGNE_SUIVANTE)

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


def test_basculer_double_dotation_creates_simulation_projets_per_dotation(
    projet, perimetre
):
    detr = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.PROCESSING)
    dsil = _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.PROCESSING)
    simulation_detr = SimulationFactory(
        enveloppe=projet.root_enveloppe(Dotation.DETR, CAMPAGNE_SUIVANTE)
    )
    simulation_dsil = SimulationFactory(
        enveloppe=projet.root_enveloppe(Dotation.DSIL, CAMPAGNE_SUIVANTE)
    )

    projet.basculer(CAMPAGNE_SUIVANTE)

    assert [
        sp.enveloppe_projet for sp in simulation_detr.simulationprojet_set.all()
    ] == [detr]
    assert [
        sp.enveloppe_projet for sp in simulation_dsil.simulationprojet_set.all()
    ] == [dsil]


def test_basculer_accepted_creates_valid_simulation_projet_with_montant(projet):
    ep = _enveloppe_projet(
        projet, Dotation.DETR, ProjetStatus.ACCEPTED, montant=Decimal("12345")
    )
    simulation = SimulationFactory(
        enveloppe=projet.root_enveloppe(Dotation.DETR, CAMPAGNE_SUIVANTE)
    )

    projet.basculer(CAMPAGNE_SUIVANTE)

    simulation_projet = SimulationProjet.objects.get(
        simulation=simulation, enveloppe_projet=ep
    )
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert simulation_projet.montant == Decimal("12345")


# -- pas de condition de date --


@pytest.mark.parametrize(
    "today, date_depot, date_programmation",
    (
        # Today: any time of the year
        ("2027-01-15", None, None),
        ("2027-11-15", None, None),
        # Date de dépôt: any time of the year
        (None, "2027-01-15", None),
        (None, "2027-05-15", None),
        (None, "2027-11-15", None),
        # Date de traitement: any time of the year
        (None, None, "2025-12-15"),
        (None, None, "2026-05-15"),
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
        assert cible in projet.campagnes_de_bascule
        projet.basculer(cible)

    ep.refresh_from_db()
    assert ep.enveloppe.annee == cible


# -- historique --


def test_basculer_creates_a_projet_action_per_dotation(projet):
    user = CollegueFactory()
    ancien = _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED)
    EnveloppeProjet.objects.supersede(ancien)
    _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.ACCEPTED)

    projet.basculer(CAMPAGNE_SUIVANTE, actor=user)

    actions = ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_BASCULE
    )
    assert {action.dotation for action in actions} == {Dotation.DETR, Dotation.DSIL}
    assert actions.count() == 2
    for action in actions:
        assert action.actor == user
        assert action.source == ProjetAction.SOURCE_TURGOT
        assert action.enveloppe == projet.root_enveloppe(
            action.dotation, CAMPAGNE_SUIVANTE
        )
    detr_action = actions.get(dotation=Dotation.DETR)
    assert (
        detr_action.action_label
        == f"Bascule DETR de la campagne {CAMPAGNE} vers {CAMPAGNE_SUIVANTE}"
    )


# -- DN --


@mock.patch("dn.sync.ds_client.DsClientBase.launch_graphql_query")
def test_basculer_does_not_call_dn(launch_graphql_query, projet):
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.ACCEPTED)
    _enveloppe_projet(projet, Dotation.DSIL, ProjetStatus.REFUSED)

    projet.basculer(CAMPAGNE_SUIVANTE)

    launch_graphql_query.assert_not_called()


# -- interaction avec le report --


@pytest.mark.skip(reason="Dépend du merge du report (ma/report-projet)")
def test_basculed_projet_can_be_reported(projet):
    _enveloppe_projet(projet, Dotation.DETR, ProjetStatus.REFUSED, CAMPAGNE_PRECEDENTE)

    projet.basculer(CAMPAGNE)

    assert projet.can_be_reported is True
    projet.reporter_without_dn()
    nouveau = EnveloppeProjet.objects.non_reportes().get(projet=projet)
    assert nouveau.status == ProjetStatus.PROCESSING
    assert nouveau.enveloppe.annee == CAMPAGNE_SUIVANTE


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
