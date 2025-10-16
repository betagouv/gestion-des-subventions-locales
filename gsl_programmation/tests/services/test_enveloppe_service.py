import pytest

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_simulation.tests.factories import SimulationFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def enveloppes():
    return DetrEnveloppeFactory.create_batch(10)


@pytest.fixture
def simulations(enveloppes):
    return [SimulationFactory(enveloppe=enveloppe) for enveloppe in enveloppes]


@pytest.mark.parametrize(
    "is_superuser, is_staff, with_perimetre, expected_count",
    [
        (True, False, False, 10),
        (False, True, False, 10),
        (True, False, True, 1),
        (False, True, True, 1),
        (False, False, True, 1),
        (False, False, False, 0),
    ],
)
def test_get_enveloppes_visible_for_a_user(
    is_superuser, is_staff, with_perimetre, expected_count, enveloppes
):
    super_user = CollegueFactory(
        is_superuser=is_superuser,
        is_staff=is_staff,
        perimetre=None if not with_perimetre else enveloppes[0].perimetre,
    )
    visible_enveloppes = EnveloppeService.get_enveloppes_visible_for_a_user(super_user)
    assert visible_enveloppes.count() == expected_count


@pytest.fixture
def perimetres():
    arrondissement_A = PerimetreArrondissementFactory()
    arrondissement_B = PerimetreArrondissementFactory()
    departemental_A = PerimetreDepartementalFactory(
        departement=arrondissement_A.departement
    )
    departemental_B = PerimetreDepartementalFactory(
        departement=arrondissement_B.departement
    )
    regional_A = PerimetreRegionalFactory(region=departemental_A.region)
    regional_B = PerimetreRegionalFactory(region=departemental_B.region)
    return {
        "arrondissements": [arrondissement_A, arrondissement_B],
        "departements": [departemental_A, departemental_B],
        "regions": [regional_A, regional_B],
    }


@pytest.fixture
def enveloppes_from_perimetre(perimetres):
    enveloppes = {
        "regions": {"dsil": []},
        "departements": {"detr": [], "dsil": []},
        "arrondissements": {"detr": [], "dsil": []},
    }
    for region in perimetres["regions"]:
        enveloppes["regions"]["dsil"].append(DsilEnveloppeFactory(perimetre=region))
    for departement in perimetres["departements"]:
        enveloppes["departements"]["detr"].append(
            DetrEnveloppeFactory(perimetre=departement)
        )
        enveloppes["departements"]["dsil"].append(
            DsilEnveloppeFactory(
                perimetre=departement,
                deleguee_by=Enveloppe.objects.get(
                    dotation=DOTATION_DSIL, perimetre__region=departement.region
                ),
            )
        )
    for arrondissement in perimetres["arrondissements"]:
        enveloppes["arrondissements"]["detr"].append(
            DetrEnveloppeFactory(
                perimetre=arrondissement,
                deleguee_by=Enveloppe.objects.get(
                    dotation=DOTATION_DETR,
                    perimetre__departement=arrondissement.departement,
                ),
            )
        )
        enveloppes["arrondissements"]["dsil"].append(
            DsilEnveloppeFactory(
                perimetre=arrondissement,
                deleguee_by=Enveloppe.objects.get(
                    dotation=DOTATION_DSIL,
                    perimetre__departement=arrondissement.departement,
                ),
            )
        )
    return enveloppes


def test_get_enveloppes_from_region_perimetre(perimetres, enveloppes_from_perimetre):
    enveloppes = EnveloppeService.get_enveloppes_from_perimetre(
        perimetres["regions"][0]
    )
    assert len(enveloppes) == 3
    assert enveloppes.filter(dotation="DETR").count() == 0
    assert enveloppes.filter(dotation="DSIL").count() == 3
    assert enveloppes.filter(perimetre__arrondissement__isnull=True).count() == 2
    assert enveloppes.filter(perimetre__departement__isnull=True).count() == 1
    for enveloppe in enveloppes:
        assert (
            perimetres["regions"][0] == enveloppe.perimetre
            or perimetres["regions"][0].contains(enveloppe.perimetre) is True
        )


def test_get_enveloppes_from_departement_perimetre(
    perimetres, enveloppes_from_perimetre
):
    enveloppes = EnveloppeService.get_enveloppes_from_perimetre(
        perimetres["departements"][0]
    )
    assert len(enveloppes) == 4
    assert enveloppes.filter(dotation="DETR").count() == 2
    assert enveloppes.filter(dotation="DSIL").count() == 2
    assert enveloppes.filter(perimetre__arrondissement__isnull=True).count() == 2
    assert enveloppes.filter(perimetre__arrondissement__isnull=False).count() == 2
    assert enveloppes.filter(perimetre__departement__isnull=True).count() == 0
    for enveloppe in enveloppes:
        assert (
            perimetres["departements"][0] == enveloppe.perimetre
            or perimetres["departements"][0].contains(enveloppe.perimetre) is True
        )


def test_get_enveloppes_from_arrondissement_perimetre(
    perimetres, enveloppes_from_perimetre
):
    enveloppes = EnveloppeService.get_enveloppes_from_perimetre(
        perimetres["arrondissements"][0]
    )
    assert len(enveloppes) == 2
    assert enveloppes.filter(dotation="DETR").count() == 1
    assert enveloppes.filter(dotation="DSIL").count() == 1
    assert enveloppes.filter(perimetre__arrondissement__isnull=True).count() == 0
    for enveloppe in enveloppes:
        assert perimetres["arrondissements"][0] == enveloppe.perimetre
