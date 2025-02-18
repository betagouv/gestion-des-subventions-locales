from decimal import Decimal

import pytest
from django.db.utils import IntegrityError

from gsl_core.models import Perimetre
from gsl_core.tests.factories import (
    DepartementFactory,
    PerimetreFactory,
    RegionFactory,
)
from gsl_programmation.models import Enveloppe
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import Simulation, SimulationProjet

pytestmark = pytest.mark.django_db


@pytest.fixture
def enveloppe_dsil():
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DSIL,
        perimetre=PerimetreFactory(
            region=RegionFactory(), departement=None, arrondissement=None
        ),
        montant=Decimal("20000000.00"),
        annee=2025,
    )


@pytest.fixture
def perimetre_departement() -> Perimetre:
    departement = DepartementFactory()
    return PerimetreFactory(departement=departement, region=departement.region)


@pytest.fixture
def enveloppe_detr(perimetre_departement):
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DETR,
        perimetre=perimetre_departement,
        montant=Decimal("2000000.00"),
        annee=2025,
    )


@pytest.fixture
def simulation_detr(enveloppe_detr):
    return Simulation.objects.create(
        title="Scénario DETR", enveloppe=enveloppe_detr, slug="simulation-detr"
    )


def test_projet_only_once_per_simulation_and_enveloppe(enveloppe_detr, simulation_detr):
    simulation_projet_un = SimulationProjet.objects.create(
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
            projet=simulation_projet_un.projet,
            montant=Decimal("15000"),
            taux=Decimal("0.52"),
        )


def test_projet_twice_per_simulation_with_different_enveloppe(
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
