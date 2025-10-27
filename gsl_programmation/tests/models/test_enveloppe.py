from datetime import UTC, datetime

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.models import Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import DotationProjetFactory, SubmittedProjetFactory
from gsl_simulation.tests.factories import SimulationFactory


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
        perimetre=perimetre_departemental,
        dossier_ds__demande_montant=20_000,
        dossier_ds__ds_date_depot=datetime(2021, 12, 1, tzinfo=UTC),
        dossier_ds__demande_dispositif_sollicite="DETR",
    )
    for projet in projets:
        DotationProjetService.create_or_update_dotation_projet_from_projet(projet)
    return projets


@pytest.fixture
def programmation_projets(perimetre_departemental, detr_enveloppe):
    for _ in range(3):
        dotation_projet = DotationProjetFactory(
            dotation=DOTATION_DETR,
            projet__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=30_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 10, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )
        ProgrammationProjetFactory(
            enveloppe=detr_enveloppe,
            status=ProgrammationProjet.STATUS_REFUSED,
            dotation_projet=dotation_projet,
        )

    for montant in (200_000, 300_000):
        dotation_projet = DotationProjetFactory(
            dotation=DOTATION_DETR,
            projet__perimetre=perimetre_departemental,
            projet__dossier_ds__demande_montant=40_000,
            projet__dossier_ds__ds_date_depot=datetime(2020, 12, 1, tzinfo=UTC),
            projet__dossier_ds__ds_date_traitement=datetime(2021, 7, 1, tzinfo=UTC),
            projet__dossier_ds__demande_dispositif_sollicite="DETR",
        )
        ProgrammationProjetFactory(
            enveloppe=detr_enveloppe,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            montant=montant,
            dotation_projet=dotation_projet,
        )


@pytest.mark.django_db
def test_enveloppe_properties(
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

    assert detr_enveloppe.dotation == "DETR"
    assert detr_enveloppe.montant == 1_000_000
    assert detr_enveloppe.validated_projets_count == 2
    assert detr_enveloppe.refused_projets_count == 3
    assert detr_enveloppe.projets_count == 9
    assert detr_enveloppe.demandeurs_count == 9
    assert detr_enveloppe.montant_asked == 20_000 * 4 + 30_000 * 3 + 40_000 * 2
    assert detr_enveloppe.accepted_montant == 200_000 + 300_000


@pytest.fixture
def enveloppes_hierarchy():
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    grandchild_enveloppe = DetrEnveloppeFactory(deleguee_by=child_enveloppe)
    return mother_enveloppe, child_enveloppe, grandchild_enveloppe


@pytest.mark.django_db
def test_root_enveloppe_not_delegated(enveloppes_hierarchy):
    mother_enveloppe, _, _ = enveloppes_hierarchy
    assert mother_enveloppe.delegation_root == mother_enveloppe


@pytest.mark.django_db
def test_get_parent_enveloppe_delegated_once(enveloppes_hierarchy):
    mother_enveloppe, child_enveloppe, _ = enveloppes_hierarchy
    assert child_enveloppe.delegation_root == mother_enveloppe


@pytest.mark.django_db
def test_get_parent_enveloppe_delegated_multiple_times(enveloppes_hierarchy):
    mother_enveloppe, _, grandchild_enveloppe = enveloppes_hierarchy
    assert grandchild_enveloppe.delegation_root == mother_enveloppe


@pytest.mark.django_db
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

        ProgrammationProjetFactory(
            enveloppe=self.detr_enveloppe,
            dotation_projet__projet__perimetre=perimetre_arr_1,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            montant=200_000,
            dotation_projet__projet__dossier_ds__demande_montant=500_000,
            dotation_projet__dotation=DOTATION_DETR,
            dotation_projet__projet__dossier_ds__ds_date_depot=datetime(
                2020, 12, 1, tzinfo=UTC
            ),
        )
        ProgrammationProjetFactory(
            enveloppe=self.detr_enveloppe,
            dotation_projet__projet__perimetre=perimetre_arr_2,
            status=ProgrammationProjet.STATUS_REFUSED,
            montant=0,
            dotation_projet__projet__dossier_ds__demande_montant=400_000,
            dotation_projet__dotation=DOTATION_DETR,
            dotation_projet__projet__dossier_ds__ds_date_depot=datetime(
                2020, 12, 1, tzinfo=UTC
            ),
        )

    def test_enveloppe_projets_processed(self):
        assert self.detr_enveloppe.enveloppe_projets_processed.count() == 2
        assert self.delegated_enveloppe_1.enveloppe_projets_processed.count() == 1
        assert self.delegated_enveloppe_2.enveloppe_projets_processed.count() == 1

    def test_accepted_montant(self):
        assert self.detr_enveloppe.accepted_montant == 200_000
        assert self.delegated_enveloppe_1.accepted_montant == 200_000
        assert self.delegated_enveloppe_2.accepted_montant == 0

    def test_validated_projets_count(self):
        assert self.detr_enveloppe.validated_projets_count == 1
        assert self.delegated_enveloppe_1.validated_projets_count == 1
        assert self.delegated_enveloppe_2.validated_projets_count == 0

    def test_refused_projets_count(self):
        assert self.detr_enveloppe.refused_projets_count == 1
        assert self.delegated_enveloppe_1.refused_projets_count == 0
        assert self.delegated_enveloppe_2.refused_projets_count == 1

    def test_projets_count(self):
        assert self.detr_enveloppe.projets_count == 2
        assert self.delegated_enveloppe_1.projets_count == 1
        assert self.delegated_enveloppe_2.projets_count == 1

    def test_demandeurs_count(self):
        assert self.detr_enveloppe.projets_count == 2
        assert self.delegated_enveloppe_1.projets_count == 1
        assert self.delegated_enveloppe_2.projets_count == 1

    def test_montant_asked(self):
        assert self.detr_enveloppe.montant_asked == 900_000
        assert self.delegated_enveloppe_1.montant_asked == 500_000
        assert self.delegated_enveloppe_2.montant_asked == 400_000
