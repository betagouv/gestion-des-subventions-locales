from datetime import date
from decimal import Decimal

import pytest

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    NaturePorteurProjetFactory,
)
from gsl_programmation.models import Enveloppe
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.models import Projet
from gsl_simulation.models import Simulation
from gsl_simulation.services.simulation_service import SimulationService
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


def test_user_with_department_and_ask_for_dsil_simulation():
    perimetre_departemental = PerimetreDepartementalFactory()
    perimetre_regional = PerimetreRegionalFactory(region=perimetre_departemental.region)
    user = CollegueFactory(perimetre=perimetre_departemental)
    DetrEnveloppeFactory(perimetre=perimetre_departemental)
    DsilEnveloppeFactory(perimetre=perimetre_regional, annee=date.today().year)
    DsilEnveloppeFactory(perimetre=perimetre_regional, annee=2024)

    SimulationService.create_simulation(user, "Test", "DSIL")

    enveloppe_dsil_deleguee = Enveloppe.objects.get(
        perimetre=perimetre_departemental,
        type=Enveloppe.TYPE_DSIL,
        annee=date.today().year,
    )

    simulation = Simulation.objects.get(enveloppe=enveloppe_dsil_deleguee)
    assert simulation.enveloppe.montant == 0
    assert simulation.slug == "test"


def test_empty_enveloppe_is_created_if_needed():
    perimetre_departemental = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=perimetre_departemental)
    assert Enveloppe.objects.count() == 0

    simulation = SimulationService.create_simulation(user, "Test", Enveloppe.TYPE_DETR)

    assert Enveloppe.objects.count() == 1
    assert simulation.enveloppe.type == Enveloppe.TYPE_DETR


def test_user_with_department_and_ask_for_detr_simulation():
    perimetre_departemental = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=perimetre_departemental)
    enveloppe_detr = DetrEnveloppeFactory(perimetre=perimetre_departemental)
    DsilEnveloppeFactory(perimetre=perimetre_departemental)

    SimulationService.create_simulation(user, "Test aussi le slug", "DETR")

    simulation = Simulation.objects.get(enveloppe=enveloppe_detr)
    assert simulation.enveloppe == enveloppe_detr
    assert simulation.enveloppe.type == Enveloppe.TYPE_DETR
    assert simulation.enveloppe.montant == enveloppe_detr.montant
    assert simulation.slug == "test-aussi-le-slug"


def test_user_without_department_and_ask_for_detr_simulation():
    perimetre_regional = PerimetreRegionalFactory()
    user = CollegueFactory(perimetre=perimetre_regional)
    DsilEnveloppeFactory(perimetre=perimetre_regional)

    with pytest.raises(ValueError):
        SimulationService.create_simulation(user, "test", "DETR")


def test_user_with_region_and_ask_for_dsil_simulation():
    perimetre_regional = PerimetreRegionalFactory()
    user = CollegueFactory(perimetre=perimetre_regional)
    enveloppe_dsil = DsilEnveloppeFactory(perimetre=perimetre_regional)

    SimulationService.create_simulation(user, "Test    avec ce titre !!", "DSIL")

    simulation = Simulation.objects.get(enveloppe=enveloppe_dsil)
    assert simulation.slug == "test-avec-ce-titre"


def test_user_with_arrondissement_and_ask_for_dsil_simulation():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    user = CollegueFactory(perimetre=perimetre_arrondissement)

    SimulationService.create_simulation(
        user, 'Test   &"@ avec ces caractères !!', "DSIL"
    )

    simulation = Simulation.objects.get(enveloppe__perimetre=perimetre_arrondissement)
    assert simulation.enveloppe.type == Enveloppe.TYPE_DSIL
    assert simulation.enveloppe.montant == 0
    assert simulation.slug == "test-avec-ces-caracteres"


def test_slug_generation():
    SimulationFactory(slug="test")
    SimulationFactory(slug="test-2")
    SimulationFactory(slug="other-test")
    SimulationFactory(slug="other-test-1")

    slug = SimulationService.get_slug("test")
    assert slug == "test-1"

    slug = SimulationService.get_slug("Test   2 !!")
    assert slug == "test-2-1"

    slug = SimulationService.get_slug("Other test")
    assert slug == "other-test-2"

    slug = SimulationService.get_slug("Other test 1")
    assert slug == "other-test-1-1"


@pytest.fixture
def simulation():
    return SimulationFactory(enveloppe=DetrEnveloppeFactory())


@pytest.fixture
def create_projets(simulation):
    epci_nature = NaturePorteurProjetFactory(label="EPCI")
    commune_nature = NaturePorteurProjetFactory(label="Communes")

    for status in ("valid", "draft", "cancelled"):
        for cout in (49, 50, 100, 150, 151):
            for montant_previsionnel in (100, 150, 151):
                SimulationProjetFactory(
                    simulation=simulation,
                    status=status,
                    montant=montant_previsionnel,
                    projet__assiette=cout,
                    projet__dossier_ds=DossierFactory(
                        demande_dispositif_sollicite="DETR",
                        porteur_de_projet_nature=epci_nature,
                    ),
                )
                SimulationProjetFactory(
                    simulation=simulation,
                    status=status,
                    montant=montant_previsionnel,
                    projet__assiette=cout,
                    projet__dossier_ds=DossierFactory(
                        demande_dispositif_sollicite="DETR",
                        porteur_de_projet_nature=commune_nature,
                    ),
                )


@pytest.mark.django_db
def test_add_filters_to_projets_qs(simulation, create_projets):
    filters = {
        "cout_min": "50",
        "cout_max": "150",
        "porteur": "EPCI",
        "montant_previsionnel_min": "100",
        "montant_previsionnel_max": "150",
        "status": ["valid"],
    }

    qs = Projet.objects.all()
    filtered_qs = SimulationService.add_filters_to_projets_qs(qs, filters, simulation)

    assert filtered_qs.count() == 6
    cout_distinct = filtered_qs.values_list("assiette", flat=True).distinct()
    assert len(cout_distinct) == 3
    assert cout_distinct[0] == Decimal("50.0")
    assert cout_distinct[1] == Decimal("100.0")
    assert cout_distinct[2] == Decimal("150.0")

    montants = filtered_qs.values_list(
        "simulationprojet__montant", flat=True
    ).distinct()
    assert len(montants) == 2
    assert montants[0] == Decimal("100.0")
    assert montants[1] == Decimal("150.0")

    dotations = filtered_qs.values_list(
        "dossier_ds__demande_dispositif_sollicite", flat=True
    ).distinct()
    assert len(dotations) == 1
    assert dotations[0] == "DETR"

    porteur = filtered_qs.values_list(
        "dossier_ds__porteur_de_projet_nature__label", flat=True
    ).distinct()
    assert len(porteur) == 1
    assert porteur[0] == "EPCI"

    assert (
        filtered_qs.values_list(
            "dossier_ds__porteur_de_projet_nature__label", flat=True
        ).distinct()[0]
        == "EPCI"
    )

    status = filtered_qs.values_list("simulationprojet__status", flat=True).distinct()
    assert len(status) == 1
    assert status[0] == "valid"
