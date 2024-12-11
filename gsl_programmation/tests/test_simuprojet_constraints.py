from decimal import Decimal

import pytest
from django.db.utils import IntegrityError

from gsl_core.tests.factories import (
    DepartementFactory,
    RegionFactory,
)
from gsl_projet.tests.factories import ProjetFactory

from ..models import Enveloppe, Scenario, SimulationProjet

pytestmark = pytest.mark.django_db


@pytest.fixture
def enveloppe_dsil():
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DSIL,
        perimetre_region=RegionFactory(),
        montant=Decimal("20000000.00"),
        annee=2025,
    )


@pytest.fixture
def enveloppe_detr():
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DETR,
        perimetre_departement=DepartementFactory(),
        montant=Decimal("2000000.00"),
        annee=2025,
    )


@pytest.fixture
def scenario_detr(enveloppe_detr):
    return Scenario.objects.create(
        title="Scénario DETR", enveloppe=enveloppe_detr, slug="scenario-detr"
    )


def test_project_only_once_per_scenario_and_enveloppe(
    enveloppe_detr, scenario_detr, enveloppe_dsil
):
    projet_un = SimulationProjet.objects.create(
        enveloppe=enveloppe_detr,
        scenario=scenario_detr,
        projet=ProjetFactory(),
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
    )
    with pytest.raises(IntegrityError):
        SimulationProjet.objects.create(
            enveloppe=enveloppe_detr,
            scenario=scenario_detr,
            projet=projet_un.projet,
            montant=Decimal("15000"),
            taux=Decimal("0.52"),
        )


def test_project_twice_per_scenario_with_different_enveloppe(
    enveloppe_detr, scenario_detr, enveloppe_dsil
):
    projet_un = SimulationProjet.objects.create(
        enveloppe=enveloppe_detr,
        scenario=scenario_detr,
        projet=ProjetFactory(),
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
    )
    SimulationProjet.objects.create(
        enveloppe=enveloppe_dsil,
        scenario=scenario_detr,
        projet=projet_un.projet,
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
    )


def test_project_validated_only_once_per_enveloppe(enveloppe_detr, scenario_detr):
    projet_without_scenario = SimulationProjet.objects.create(
        enveloppe=enveloppe_detr,
        projet=ProjetFactory(),
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
        status=SimulationProjet.STATUS_VALID,
    )
    with pytest.raises(IntegrityError):
        SimulationProjet.objects.create(
            enveloppe=enveloppe_detr,
            scenario=scenario_detr,
            projet=projet_without_scenario.projet,
            montant=Decimal("15000"),
            taux=Decimal("0.52"),
            status=SimulationProjet.STATUS_VALID,
        )
