import pytest

from gsl_core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.service.enveloppe_service import EnveloppeService
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory

pytestmark = pytest.mark.django_db


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
