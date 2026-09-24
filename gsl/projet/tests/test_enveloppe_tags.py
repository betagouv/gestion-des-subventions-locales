from datetime import UTC, datetime

import pytest

from gsl.simulation.tests.factories import SimulationFactory
from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

from ..constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from ..models import Projet
from ..services.enveloppe_projet_services import EnveloppeProjetService
from ..templatetags.enveloppe_tags import enveloppe_summary_line
from .factories import EnveloppeProjetFactory, SubmittedProjetFactory

pytestmark = pytest.mark.django_db


def summary(enveloppe):
    return enveloppe_summary_line({}, enveloppe)


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        annee=2021, montant=1_000_000, perimetre=perimetre_departemental
    )


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def submitted_projets(perimetre_departemental):
    projets = SubmittedProjetFactory.create_batch(
        4,
        dossier_ds__perimetre=perimetre_departemental,
        dossier_ds__demande_montant=20_000,
        dossier_ds__ds_date_depot=datetime(2021, 12, 1, tzinfo=UTC),
        dossier_ds__demande_dispositif_sollicite="DETR",
    )
    for projet in projets:
        EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet(projet)
    return projets


@pytest.fixture
def programmation_projets(perimetre_departemental, detr_enveloppe):
    for _ in range(3):
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_REFUSED,
            enveloppe=detr_enveloppe,
            projet__dossier_ds__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=30_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 10, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )

    for montant in (200_000, 300_000):
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=detr_enveloppe,
            montant=montant,
            projet__dossier_ds__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=40_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 7, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )


def test_summary_line(
    detr_enveloppe, simulation, programmation_projets, submitted_projets
):
    assert Projet.objects.count() == 4 + 3 + 2  # = 9

    projet_filter_by_perimetre = Projet.objects.for_perimetre(detr_enveloppe.perimetre)
    assert projet_filter_by_perimetre.count() == 4 + 3 + 2  # = 9

    projet_filter_by_perimetre_and_dotation = projet_filter_by_perimetre.filter(
        dossier_ds__demande_dispositif_sollicite="DETR"
    )
    assert projet_filter_by_perimetre_and_dotation.count() == 4 + 3 + 2  # = 9

    projet_qs_submitted_before_the_end_of_the_year = (
        projet_filter_by_perimetre_and_dotation.filter(
            dossier_ds__ds_date_depot__lt=datetime(
                simulation.enveloppe.annee + 1, 1, 1, tzinfo=UTC
            ),
        )
    )
    assert projet_qs_submitted_before_the_end_of_the_year.count() == 4 + 3 + 2  # = 9

    context = summary(detr_enveloppe)
    assert context["enveloppe"] is detr_enveloppe
    assert context["validated_projets_count"] == 2
    assert context["refused_projets_count"] == 3
    assert context["projets_count"] == 9
    assert context["demandeurs_count"] == 9
    assert context["montant_asked"] == 20_000 * 4 + 30_000 * 3 + 40_000 * 2
    assert context["accepted_montant"] == 200_000 + 300_000
    assert context["reste_a_attribuer"] == 1_000_000 - (200_000 + 300_000)


def test_summary_line_default_rendering_options(detr_enveloppe):
    context = summary(detr_enveloppe)
    assert context["level"] == 1
    assert context["hide_actions"] is False
    assert context["oob_swap"] is False


def test_summary_line_forwards_rendering_options(detr_enveloppe):
    context = enveloppe_summary_line(
        {"csrf_token": "a-token"},
        detr_enveloppe,
        level=2,
        hide_actions=True,
        oob_swap=True,
    )
    assert context["level"] == 2
    assert context["hide_actions"] is True
    assert context["oob_swap"] is True
    assert context["csrf_token"] == "a-token"


class TestDelegatedEnveloppe:
    def setup_method(self):
        self.detr_enveloppe = DetrEnveloppeFactory()

        perimetre_arrondissements = PerimetreArrondissementFactory.create_batch(
            2,
            arrondissement__departement=self.detr_enveloppe.perimetre.departement,
            departement=self.detr_enveloppe.perimetre.departement,
            region=self.detr_enveloppe.perimetre.region,
        )

        self.delegated_enveloppe_1 = DetrEnveloppeFactory(
            perimetre=perimetre_arrondissements[0],
            deleguee_by=self.detr_enveloppe,
            annee=2021,
        )
        self.delegated_enveloppe_2 = DetrEnveloppeFactory(
            perimetre=perimetre_arrondissements[1],
            deleguee_by=self.detr_enveloppe,
            annee=2021,
        )

        perimetre_arr_1, perimetre_arr_2 = perimetre_arrondissements

        EnveloppeProjetFactory(
            enveloppe=self.detr_enveloppe,
            projet__dossier_ds__perimetre=perimetre_arr_1,
            status=PROJET_STATUS_ACCEPTED,
            montant=200_000,
            projet__dossier_ds__demande_montant=500_000,
            dotation=DOTATION_DETR,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )
        EnveloppeProjetFactory(
            enveloppe=self.detr_enveloppe,
            projet__dossier_ds__perimetre=perimetre_arr_2,
            status=PROJET_STATUS_REFUSED,
            montant=0,
            projet__dossier_ds__demande_montant=400_000,
            dotation=DOTATION_DETR,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )

    def test_accepted_montant(self):
        assert summary(self.detr_enveloppe)["accepted_montant"] == 200_000
        assert summary(self.delegated_enveloppe_1)["accepted_montant"] == 200_000
        assert summary(self.delegated_enveloppe_2)["accepted_montant"] == 0

    def test_validated_projets_count(self):
        assert summary(self.detr_enveloppe)["validated_projets_count"] == 1
        assert summary(self.delegated_enveloppe_1)["validated_projets_count"] == 1
        assert summary(self.delegated_enveloppe_2)["validated_projets_count"] == 0

    def test_refused_projets_count(self):
        assert summary(self.detr_enveloppe)["refused_projets_count"] == 1
        assert summary(self.delegated_enveloppe_1)["refused_projets_count"] == 0
        assert summary(self.delegated_enveloppe_2)["refused_projets_count"] == 1

    def test_projets_count(self):
        assert summary(self.detr_enveloppe)["projets_count"] == 2
        assert summary(self.delegated_enveloppe_1)["projets_count"] == 1
        assert summary(self.delegated_enveloppe_2)["projets_count"] == 1

    def test_demandeurs_count(self):
        assert summary(self.detr_enveloppe)["demandeurs_count"] == 2
        assert summary(self.delegated_enveloppe_1)["demandeurs_count"] == 1
        assert summary(self.delegated_enveloppe_2)["demandeurs_count"] == 1

    def test_montant_asked(self):
        assert summary(self.detr_enveloppe)["montant_asked"] == 900_000
        assert summary(self.delegated_enveloppe_1)["montant_asked"] == 500_000
        assert summary(self.delegated_enveloppe_2)["montant_asked"] == 400_000


class TestDelegatedEnveloppeWithTreeLevels:
    def setup_method(self):
        arrondissement = PerimetreArrondissementFactory()
        departement = PerimetreDepartementalFactory(
            departement=arrondissement.departement, region=arrondissement.region
        )
        region = PerimetreRegionalFactory(region=arrondissement.region)

        self.dsil_enveloppe = DsilEnveloppeFactory(perimetre=region, annee=2021)
        self.dsil_enveloppe_dep = DsilEnveloppeFactory(
            perimetre=departement, deleguee_by=self.dsil_enveloppe, annee=2021
        )
        self.dsil_enveloppe_arr = DsilEnveloppeFactory(
            perimetre=arrondissement, deleguee_by=self.dsil_enveloppe_dep, annee=2021
        )

        EnveloppeProjetFactory(
            enveloppe=self.dsil_enveloppe,
            dotation=DOTATION_DSIL,
            projet__dossier_ds__perimetre=arrondissement,
            status=PROJET_STATUS_ACCEPTED,
            montant=200_000,
            projet__dossier_ds__demande_montant=500_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )
        EnveloppeProjetFactory(
            enveloppe=self.dsil_enveloppe,
            dotation=DOTATION_DSIL,
            projet__dossier_ds__perimetre=arrondissement,
            status=PROJET_STATUS_REFUSED,
            montant=0,
            projet__dossier_ds__demande_montant=400_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )

    def test_accepted_montant(self):
        assert summary(self.dsil_enveloppe)["accepted_montant"] == 200_000
        assert summary(self.dsil_enveloppe_dep)["accepted_montant"] == 200_000
        assert summary(self.dsil_enveloppe_arr)["accepted_montant"] == 200_000

    def test_validated_projets_count(self):
        assert summary(self.dsil_enveloppe)["validated_projets_count"] == 1
        assert summary(self.dsil_enveloppe_dep)["validated_projets_count"] == 1
        assert summary(self.dsil_enveloppe_arr)["validated_projets_count"] == 1

    def test_refused_projets_count(self):
        assert summary(self.dsil_enveloppe)["refused_projets_count"] == 1
        assert summary(self.dsil_enveloppe_dep)["refused_projets_count"] == 1
        assert summary(self.dsil_enveloppe_arr)["refused_projets_count"] == 1

    def test_projets_count(self):
        assert summary(self.dsil_enveloppe)["projets_count"] == 2
        assert summary(self.dsil_enveloppe_dep)["projets_count"] == 2
        assert summary(self.dsil_enveloppe_arr)["projets_count"] == 2

    def test_demandeurs_count(self):
        assert summary(self.dsil_enveloppe)["demandeurs_count"] == 2
        assert summary(self.dsil_enveloppe_dep)["demandeurs_count"] == 2
        assert summary(self.dsil_enveloppe_arr)["demandeurs_count"] == 2

    def test_montant_asked(self):
        assert summary(self.dsil_enveloppe)["montant_asked"] == 900_000
        assert summary(self.dsil_enveloppe_dep)["montant_asked"] == 900_000
        assert summary(self.dsil_enveloppe_arr)["montant_asked"] == 900_000


class TestExcludeInactiveProjets:
    DEMANDE_MONTANT = 20_000

    def setup_method(self):
        self.enveloppe = DetrEnveloppeFactory(annee=2021, montant=1_000_000)
        perimetre = self.enveloppe.perimetre
        depot = datetime(2021, 6, 1, tzinfo=UTC)

        # 2 active accepted projets
        for montant in (100_000, 150_000):
            EnveloppeProjetFactory(
                dotation=DOTATION_DETR,
                status=PROJET_STATUS_ACCEPTED,
                enveloppe=self.enveloppe,
                montant=montant,
                projet__dossier_ds__perimetre=perimetre,
                projet__dossier_ds__demande_montant=self.DEMANDE_MONTANT,
                projet__dossier_ds__ds_date_depot=depot,
            )

        # 1 active refused projet
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_REFUSED,
            enveloppe=self.enveloppe,
            montant=0,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=self.DEMANDE_MONTANT,
            projet__dossier_ds__ds_date_depot=depot,
        )

        # 1 active projet without programmation (eligible, not yet programmed)
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_PROCESSING,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=self.DEMANDE_MONTANT,
            projet__dossier_ds__ds_date_depot=depot,
        )

        # 1 INACTIVE accepted projet — must be excluded everywhere
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_ACCEPTED,
            enveloppe=self.enveloppe,
            montant=999_000,
            projet__dossier_ds__is_active=False,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=999_000,
            projet__dossier_ds__ds_date_depot=depot,
        )

        # 1 INACTIVE projet without programmation — must be excluded from included
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            projet__dossier_ds__is_active=False,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=888_000,
            projet__dossier_ds__ds_date_depot=depot,
        )

    def test_montant_asked(self):
        assert summary(self.enveloppe)["montant_asked"] == self.DEMANDE_MONTANT * 4

    def test_accepted_montant(self):
        assert summary(self.enveloppe)["accepted_montant"] == 100_000 + 150_000

    def test_reste_a_attribuer(self):
        assert summary(self.enveloppe)["reste_a_attribuer"] == 1_000_000 - 250_000

    def test_validated_projets_count(self):
        assert summary(self.enveloppe)["validated_projets_count"] == 2

    def test_refused_projets_count(self):
        assert summary(self.enveloppe)["refused_projets_count"] == 1

    def test_projets_count(self):
        assert summary(self.enveloppe)["projets_count"] == 4

    def test_demandeurs_count(self):
        assert summary(self.enveloppe)["demandeurs_count"] == 4
