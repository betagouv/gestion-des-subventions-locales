import pytest

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    SimulationFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def enveloppes():
    return DetrEnveloppeFactory.create_batch(10)


@pytest.fixture
def simulations(enveloppes):
    return [SimulationFactory(enveloppe=enveloppe) for enveloppe in enveloppes]


@pytest.mark.parametrize(
    "is_staff, is_superuser, with_perimetre, expected_count",
    [
        (True, False, False, 10),
        (False, True, True, 1),
        (False, True, False, 10),
        (False, True, True, 1),
        (False, False, False, 0),
        (False, False, True, 1),
    ],
)
def test_get_enveloppes_visible_for_a_user(
    is_staff, is_superuser, with_perimetre, expected_count, enveloppes
):
    super_user = CollegueFactory(
        is_staff=is_staff,
        is_superuser=is_superuser,
        perimetre=None if not with_perimetre else enveloppes[0].perimetre,
    )
    visible_enveloppes = EnveloppeService.get_enveloppes_visible_for_a_user(super_user)
    assert visible_enveloppes.count() == expected_count


def test_get_enveloppes_from_departement_perimetre():
    departemental_perimetre = PerimetreDepartementalFactory()
    other_departemental_perimetre = PerimetreDepartementalFactory()
    DetrEnveloppeFactory(perimetre=departemental_perimetre)
    DetrEnveloppeFactory(perimetre=other_departemental_perimetre)

    regional_perimetre = PerimetreRegionalFactory(region=departemental_perimetre.region)
    regional_dsil_enveloppe = DsilEnveloppeFactory(perimetre=regional_perimetre)
    DsilEnveloppeFactory(
        perimetre=departemental_perimetre, deleguee_by=regional_dsil_enveloppe
    )

    enveloppes = EnveloppeService.get_enveloppes_from_perimetre(departemental_perimetre)
    assert len(enveloppes) == 2
    assert enveloppes.filter(deleguee_by=regional_dsil_enveloppe).count() == 1


def test_get_enveloppes_from_regional_perimetre():
    departemental_perimetre = PerimetreDepartementalFactory()
    other_departemental_perimetre = PerimetreDepartementalFactory()
    DetrEnveloppeFactory(perimetre=departemental_perimetre)
    DetrEnveloppeFactory(perimetre=other_departemental_perimetre)

    regional_perimetre = PerimetreRegionalFactory(region=departemental_perimetre.region)
    regional_dsil_enveloppe = DsilEnveloppeFactory(perimetre=regional_perimetre)
    DsilEnveloppeFactory(
        perimetre=departemental_perimetre, deleguee_by=regional_dsil_enveloppe
    )

    other_regional_perimetre = PerimetreRegionalFactory()
    DsilEnveloppeFactory(perimetre=other_regional_perimetre)

    enveloppes = EnveloppeService.get_enveloppes_from_perimetre(regional_perimetre)
    assert enveloppes.count() == 1
