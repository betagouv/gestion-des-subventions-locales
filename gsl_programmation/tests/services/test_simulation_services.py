from datetime import date

import pytest

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe, Simulation
from gsl_programmation.services import SimulationService
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    SimulationFactory,
)

pytestmark = pytest.mark.django_db


def test_user_with_department_and_ask_for_dsil_simulation():
    perimetre_departemental = PerimetreDepartementalFactory()
    perimetre_regional = PerimetreRegionalFactory(region=perimetre_departemental.region)
    user = CollegueFactory(perimetre=perimetre_departemental)
    DetrEnveloppeFactory(perimetre=perimetre_departemental)
    enveloppe_dsil = DsilEnveloppeFactory(
        perimetre=perimetre_regional, annee=date.today().year
    )
    DsilEnveloppeFactory(perimetre=perimetre_regional, annee=2024)

    SimulationService.create_simulation(user, "Test", "DSIL")

    simulation = Simulation.objects.get(enveloppe=enveloppe_dsil)
    assert simulation.enveloppe == enveloppe_dsil
    assert simulation.enveloppe.type == Enveloppe.TYPE_DSIL
    assert simulation.enveloppe.montant == enveloppe_dsil.montant
    assert simulation.slug == "test"


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


def test_user_without_department_and_ask_for_dsil_simulation():
    perimetre_regional = PerimetreRegionalFactory()
    user = CollegueFactory(perimetre=perimetre_regional)
    enveloppe_dsil = DsilEnveloppeFactory(perimetre=perimetre_regional)

    SimulationService.create_simulation(user, "Test    avec ce titre !!", "DSIL")

    simulation = Simulation.objects.get(enveloppe=enveloppe_dsil)
    assert simulation.enveloppe == enveloppe_dsil
    assert simulation.enveloppe.type == Enveloppe.TYPE_DSIL
    assert simulation.enveloppe.montant == enveloppe_dsil.montant
    assert simulation.slug == "test-avec-ce-titre"


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
