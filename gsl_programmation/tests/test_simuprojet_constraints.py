from decimal import Decimal

import pytest
from django.db.utils import IntegrityError

from gsl_core.tests.factories import (
    DepartementFactory,
    RegionFactory,
)
from gsl_projet.tests.factories import ProjetFactory

from ..models import Enveloppe, Simulation, SimulationProjet

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
def simulation_detr(enveloppe_detr):
    return Simulation.objects.create(
        title="Scénario DETR", enveloppe=enveloppe_detr, slug="simulation-detr"
    )


def test_project_only_once_per_simulation_and_enveloppe(
    enveloppe_detr, simulation_detr, enveloppe_dsil
):
    projet_un = SimulationProjet.objects.create(
        enveloppe=enveloppe_detr,
        simulation=simulation_detr,
        projet=ProjetFactory(),
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
    )
    with pytest.raises(IntegrityError):
        SimulationProjet.objects.create(
            enveloppe=enveloppe_detr,
            simulation=simulation_detr,
            projet=projet_un.projet,
            montant=Decimal("15000"),
            taux=Decimal("0.52"),
        )


def test_project_twice_per_simulation_with_different_enveloppe(
    enveloppe_detr, simulation_detr, enveloppe_dsil
):
    projet_un = SimulationProjet.objects.create(
        enveloppe=enveloppe_detr,
        simulation=simulation_detr,
        projet=ProjetFactory(),
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
    )
    SimulationProjet.objects.create(
        enveloppe=enveloppe_dsil,
        simulation=simulation_detr,
        projet=projet_un.projet,
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
    )


def test_project_validated_only_once_per_enveloppe(enveloppe_detr, simulation_detr):
    projet_without_simulation = SimulationProjet.objects.create(
        enveloppe=enveloppe_detr,
        projet=ProjetFactory(),
        montant=Decimal("15000"),
        taux=Decimal("0.52"),
        status=SimulationProjet.STATUS_VALID,
    )
    with pytest.raises(IntegrityError):
        SimulationProjet.objects.create(
            enveloppe=enveloppe_detr,
            simulation=simulation_detr,
            projet=projet_without_simulation.projet,
            montant=Decimal("15000"),
            taux=Decimal("0.52"),
            status=SimulationProjet.STATUS_VALID,
        )
