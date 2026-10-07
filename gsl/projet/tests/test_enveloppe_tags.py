from datetime import UTC, datetime

import pytest

from gsl.core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

from ..constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from ..templatetags.enveloppe_tags import enveloppe_summary_line
from .factories import EnveloppeProjetFactory

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
def submitted_projets(perimetre_departemental, detr_enveloppe):
    for _ in range(4):
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.PROCESSING,
            enveloppe=detr_enveloppe,
            projet__dossier_ds__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=20_000,
            projet__dossier_ds__ds_date_depot=datetime(2021, 12, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )


@pytest.fixture
def projets_programmes(perimetre_departemental, detr_enveloppe):
    for _ in range(3):
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.REFUSED,
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
            status=ProjetStatus.ACCEPTED,
            enveloppe=detr_enveloppe,
            montant=montant,
            projet__dossier_ds__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=40_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 7, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )


def test_summary_line(detr_enveloppe, projets_programmes, submitted_projets):
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
            parent=self.detr_enveloppe,
            annee=2021,
        )
        self.delegated_enveloppe_2 = DetrEnveloppeFactory(
            perimetre=perimetre_arrondissements[1],
            parent=self.detr_enveloppe,
            annee=2021,
        )

        perimetre_arr_1, perimetre_arr_2 = perimetre_arrondissements

        EnveloppeProjetFactory(
            enveloppe=self.detr_enveloppe,
            projet__dossier_ds__perimetre=perimetre_arr_1,
            status=ProjetStatus.ACCEPTED,
            montant=200_000,
            projet__dossier_ds__demande_montant=500_000,
            dotation=DOTATION_DETR,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )
        EnveloppeProjetFactory(
            enveloppe=self.detr_enveloppe,
            projet__dossier_ds__perimetre=perimetre_arr_2,
            status=ProjetStatus.REFUSED,
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
            perimetre=departement, parent=self.dsil_enveloppe, annee=2021
        )
        self.dsil_enveloppe_arr = DsilEnveloppeFactory(
            perimetre=arrondissement, parent=self.dsil_enveloppe_dep, annee=2021
        )

        EnveloppeProjetFactory(
            enveloppe=self.dsil_enveloppe,
            dotation=DOTATION_DSIL,
            projet__dossier_ds__perimetre=arrondissement,
            status=ProjetStatus.ACCEPTED,
            montant=200_000,
            projet__dossier_ds__demande_montant=500_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )
        EnveloppeProjetFactory(
            enveloppe=self.dsil_enveloppe,
            dotation=DOTATION_DSIL,
            projet__dossier_ds__perimetre=arrondissement,
            status=ProjetStatus.REFUSED,
            projet__dossier_ds__demande_montant=400_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )

        # Outside the arrondissement, inside the departement
        EnveloppeProjetFactory(
            enveloppe=self.dsil_enveloppe,
            dotation=DOTATION_DSIL,
            projet__dossier_ds__perimetre=PerimetreArrondissementFactory(
                arrondissement__departement=arrondissement.departement
            ),
            status=ProjetStatus.ACCEPTED,
            montant=50_000,
            projet__dossier_ds__demande_montant=60_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )
        # Outside the departement, inside the region
        EnveloppeProjetFactory(
            enveloppe=self.dsil_enveloppe,
            dotation=DOTATION_DSIL,
            projet__dossier_ds__perimetre=PerimetreDepartementalFactory(
                departement__region=arrondissement.region,
                region=arrondissement.region,
            ),
            status=ProjetStatus.REFUSED,
            projet__dossier_ds__demande_montant=70_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
        )

    def test_accepted_montant(self):
        assert summary(self.dsil_enveloppe)["accepted_montant"] == 250_000
        assert summary(self.dsil_enveloppe_dep)["accepted_montant"] == 250_000
        assert summary(self.dsil_enveloppe_arr)["accepted_montant"] == 200_000

    def test_validated_projets_count(self):
        assert summary(self.dsil_enveloppe)["validated_projets_count"] == 2
        assert summary(self.dsil_enveloppe_dep)["validated_projets_count"] == 2
        assert summary(self.dsil_enveloppe_arr)["validated_projets_count"] == 1

    def test_refused_projets_count(self):
        assert summary(self.dsil_enveloppe)["refused_projets_count"] == 2
        assert summary(self.dsil_enveloppe_dep)["refused_projets_count"] == 1
        assert summary(self.dsil_enveloppe_arr)["refused_projets_count"] == 1

    def test_projets_count(self):
        assert summary(self.dsil_enveloppe)["projets_count"] == 4
        assert summary(self.dsil_enveloppe_dep)["projets_count"] == 3
        assert summary(self.dsil_enveloppe_arr)["projets_count"] == 2

    def test_demandeurs_count(self):
        assert summary(self.dsil_enveloppe)["demandeurs_count"] == 4
        assert summary(self.dsil_enveloppe_dep)["demandeurs_count"] == 3
        assert summary(self.dsil_enveloppe_arr)["demandeurs_count"] == 2

    def test_montant_asked(self):
        assert summary(self.dsil_enveloppe)["montant_asked"] == 1_030_000
        assert summary(self.dsil_enveloppe_dep)["montant_asked"] == 960_000
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
                status=ProjetStatus.ACCEPTED,
                enveloppe=self.enveloppe,
                montant=montant,
                projet__dossier_ds__perimetre=perimetre,
                projet__dossier_ds__demande_montant=self.DEMANDE_MONTANT,
                projet__dossier_ds__ds_date_depot=depot,
            )

        # 1 active refused projet
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.REFUSED,
            enveloppe=self.enveloppe,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=self.DEMANDE_MONTANT,
            projet__dossier_ds__ds_date_depot=depot,
        )

        # 1 active projet without programmation (eligible, not yet programmed)
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.PROCESSING,
            enveloppe=self.enveloppe,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=self.DEMANDE_MONTANT,
            projet__dossier_ds__ds_date_depot=depot,
        )

        # 1 INACTIVE accepted projet — must be excluded everywhere
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
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
            status=ProjetStatus.PROCESSING,
            enveloppe=self.enveloppe,
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


class TestOnlyEnveloppeProjetsLinkedToTheEnveloppe:
    """
    `included` only holds the EnveloppeProjet linked to the enveloppe, and
    `processed` only those of them carrying a final status.
    """

    def setup_method(self):
        self.enveloppe = DetrEnveloppeFactory(annee=2021, montant=1_000_000)
        self.next_year_enveloppe = DetrEnveloppeFactory(
            annee=2022, perimetre=self.enveloppe.perimetre
        )
        perimetre = self.enveloppe.perimetre

        # Linked to the enveloppe: processing, accepted, refused and dismissed
        for status, montant in (
            (ProjetStatus.PROCESSING, None),
            (ProjetStatus.ACCEPTED, 100_000),
            (ProjetStatus.REFUSED, None),
            (ProjetStatus.DISMISSED, None),
        ):
            EnveloppeProjetFactory(
                dotation=DOTATION_DETR,
                status=status,
                enveloppe=self.enveloppe,
                montant=montant,
                projet__dossier_ds__perimetre=perimetre,
                projet__dossier_ds__demande_montant=10_000,
                projet__dossier_ds__ds_date_depot=datetime(2021, 6, 1, tzinfo=UTC),
                projet__dossier_ds__ds_date_traitement=None
                if status == ProjetStatus.PROCESSING
                else datetime(2022, 3, 1, tzinfo=UTC),
            )

        # Linked to the enveloppe although deposited after its year
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            enveloppe=self.enveloppe,
            montant=50_000,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=20_000,
            projet__dossier_ds__ds_date_depot=datetime(2022, 2, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2022, 3, 1, tzinfo=UTC),
        )

        # Deposited during the enveloppe's year, but linked to the next year one
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.PROCESSING,
            enveloppe=self.next_year_enveloppe,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=300_000,
            projet__dossier_ds__ds_date_depot=datetime(2021, 6, 1, tzinfo=UTC),
        )
        EnveloppeProjetFactory(
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            enveloppe=self.next_year_enveloppe,
            montant=400_000,
            projet__dossier_ds__perimetre=perimetre,
            projet__dossier_ds__demande_montant=400_000,
            projet__dossier_ds__ds_date_depot=datetime(2021, 6, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2022, 3, 1, tzinfo=UTC),
        )

        self._create_enveloppe_projets_linked_to_other_enveloppes()

    def _create_enveloppe_projets_linked_to_other_enveloppes(self):
        perimetre = self.enveloppe.perimetre
        region = perimetre.region
        other_departement_perimetre = PerimetreDepartementalFactory(
            departement__region=region, region=region
        )
        perimetre_region = PerimetreRegionalFactory(region=region)

        previous_year_enveloppe = DetrEnveloppeFactory(annee=2020, perimetre=perimetre)
        other_departement_enveloppe = DetrEnveloppeFactory(
            annee=2021, perimetre=other_departement_perimetre
        )
        dsil_enveloppe = DsilEnveloppeFactory(annee=2021, perimetre=perimetre_region)

        for enveloppe, dotation, projet_perimetre in (
            # Same perimetre, previous year, processed during the enveloppe's year
            (previous_year_enveloppe, DOTATION_DETR, perimetre),
            # Same year, perimetre not included in the enveloppe's one
            (other_departement_enveloppe, DOTATION_DETR, other_departement_perimetre),
            # Same year, perimetre including the enveloppe's one, other dotation
            (dsil_enveloppe, DOTATION_DSIL, perimetre),
        ):
            for status, montant in (
                (ProjetStatus.PROCESSING, None),
                (ProjetStatus.ACCEPTED, 600_000),
                (ProjetStatus.REFUSED, None),
            ):
                EnveloppeProjetFactory(
                    dotation=dotation,
                    status=status,
                    enveloppe=enveloppe,
                    montant=montant,
                    projet__dossier_ds__perimetre=projet_perimetre,
                    projet__dossier_ds__demande_montant=700_000,
                    projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
                    projet__dossier_ds__ds_date_traitement=datetime(
                        2021, 3, 1, tzinfo=UTC
                    ),
                )

    def test_projets_count(self):
        assert summary(self.enveloppe)["projets_count"] == 5
        assert summary(self.next_year_enveloppe)["projets_count"] == 2

    def test_demandeurs_count(self):
        assert summary(self.enveloppe)["demandeurs_count"] == 5
        assert summary(self.next_year_enveloppe)["demandeurs_count"] == 2

    def test_montant_asked(self):
        assert summary(self.enveloppe)["montant_asked"] == 10_000 * 4 + 20_000
        assert summary(self.next_year_enveloppe)["montant_asked"] == 700_000

    def test_validated_projets_count(self):
        assert summary(self.enveloppe)["validated_projets_count"] == 2
        assert summary(self.next_year_enveloppe)["validated_projets_count"] == 1

    def test_refused_projets_count(self):
        assert summary(self.enveloppe)["refused_projets_count"] == 1
        assert summary(self.next_year_enveloppe)["refused_projets_count"] == 0

    def test_accepted_montant(self):
        assert summary(self.enveloppe)["accepted_montant"] == 100_000 + 50_000
        assert summary(self.next_year_enveloppe)["accepted_montant"] == 400_000

    def test_reste_a_attribuer(self):
        assert summary(self.enveloppe)["reste_a_attribuer"] == 1_000_000 - 150_000


class TestDelegatedEnveloppeOnlyCountsEnveloppeProjetsLinkedToItsRoot:
    def setup_method(self):
        self.detr_enveloppe = DetrEnveloppeFactory(annee=2021)
        perimetre_arrondissement, other_perimetre_arrondissement = (
            PerimetreArrondissementFactory.create_batch(
                2,
                arrondissement__departement=self.detr_enveloppe.perimetre.departement,
                departement=self.detr_enveloppe.perimetre.departement,
                region=self.detr_enveloppe.perimetre.region,
            )
        )
        self.delegated_enveloppe = DetrEnveloppeFactory(
            perimetre=perimetre_arrondissement, parent=self.detr_enveloppe, annee=2021
        )
        next_year_enveloppe = DetrEnveloppeFactory(
            annee=2022, perimetre=self.detr_enveloppe.perimetre
        )
        previous_year_enveloppe = DetrEnveloppeFactory(
            annee=2020, perimetre=self.detr_enveloppe.perimetre
        )

        EnveloppeProjetFactory(
            enveloppe=self.detr_enveloppe,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            montant=200_000,
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            projet__dossier_ds__demande_montant=500_000,
            projet__dossier_ds__ds_date_depot=datetime(2021, 6, 1, tzinfo=UTC),
        )
        # Same arrondissement, deposited in 2021, but linked to the 2022 enveloppe
        EnveloppeProjetFactory(
            enveloppe=next_year_enveloppe,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            montant=300_000,
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            projet__dossier_ds__demande_montant=400_000,
            projet__dossier_ds__ds_date_depot=datetime(2021, 6, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2022, 3, 1, tzinfo=UTC),
        )
        # Linked to the root enveloppe, but in an arrondissement outside the
        # delegated enveloppe's perimetre
        EnveloppeProjetFactory(
            enveloppe=self.detr_enveloppe,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            montant=100_000,
            projet__dossier_ds__perimetre=other_perimetre_arrondissement,
            projet__dossier_ds__demande_montant=150_000,
            projet__dossier_ds__ds_date_depot=datetime(2021, 6, 1, tzinfo=UTC),
        )
        # Same arrondissement, linked to the previous year enveloppe
        EnveloppeProjetFactory(
            enveloppe=previous_year_enveloppe,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            montant=250_000,
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            projet__dossier_ds__demande_montant=350_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 3, 1, tzinfo=UTC),
        )

    def test_projets_count(self):
        assert summary(self.delegated_enveloppe)["projets_count"] == 1

    def test_montant_asked(self):
        assert summary(self.delegated_enveloppe)["montant_asked"] == 500_000

    def test_accepted_montant(self):
        assert summary(self.delegated_enveloppe)["accepted_montant"] == 200_000
