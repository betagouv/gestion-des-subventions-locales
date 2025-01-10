from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from gsl_core.models import Perimetre
from gsl_core.tests.factories import (
    ArrondissementFactory,
    PerimetreFactory,
)

from ..models import Enveloppe

pytestmark = pytest.mark.django_db


@pytest.fixture
def arrondissement():
    return ArrondissementFactory()


@pytest.fixture
def region(departement):
    return departement.region


@pytest.fixture
def departement(arrondissement):
    return arrondissement.departement


@pytest.fixture
def perimetre_region(region) -> Perimetre:
    return PerimetreFactory(region=region, departement=None, arrondissement=None)


@pytest.fixture
def perimetre_departement(departement) -> Perimetre:
    return PerimetreFactory(
        region=departement.region,
        departement=departement,
        arrondissement=None,
    )


@pytest.fixture
def perimetre_arrondissement(arrondissement) -> Perimetre:
    return PerimetreFactory(
        region=arrondissement.departement.region,
        departement=arrondissement.departement,
        arrondissement=arrondissement,
    )


def test_dsil_not_delegated_must_have_regional_perimeter(perimetre_departement):
    with pytest.raises(ValidationError):
        enveloppe = Enveloppe(
            type=Enveloppe.TYPE_DSIL,
            montant=Decimal("123.00"),
            annee=2025,
            perimetre=perimetre_departement,
        )
        enveloppe.full_clean()


def test_detr_not_delegated_must_have_departemental_perimeter(perimetre_arrondissement):
    with pytest.raises(ValidationError):
        enveloppe = Enveloppe(
            type=Enveloppe.TYPE_DETR,
            montant=Decimal("123.00"),
            annee=2025,
            perimetre=perimetre_arrondissement,
        )
        enveloppe.full_clean()


def test_correct_dsil_non_delegated(perimetre_region):
    enveloppe = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_region,
    )
    enveloppe.full_clean()


@pytest.fixture
def dsil_enveloppe(perimetre_region):
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_region,
    )


def test_correct_dsil_delegated_to_departement(dsil_enveloppe, perimetre_departement):
    enveloppe_departement = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_departement,
        deleguee_by=dsil_enveloppe,
    )
    enveloppe_departement.full_clean()


def test_correct_dsil_delegated_to_arrondissement(
    dsil_enveloppe, perimetre_departement, perimetre_arrondissement
):
    enveloppe_departement = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_departement,
        deleguee_by=dsil_enveloppe,
    )
    enveloppe_departement.full_clean()
    enveloppe_departement.save()
    enveloppe_arrondissement = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_arrondissement,
        deleguee_by=enveloppe_departement,
    )
    enveloppe_arrondissement.full_clean()


def test_correct_detr_non_delegated(perimetre_departement):
    enveloppe = Enveloppe(
        type=Enveloppe.TYPE_DETR,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_departement,
    )
    enveloppe.full_clean()


@pytest.fixture
def detr_enveloppe(perimetre_departement):
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DETR,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_departement,
    )


def test_correct_detr_delegated(detr_enveloppe, perimetre_arrondissement):
    enveloppe = Enveloppe(
        type=Enveloppe.TYPE_DETR,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre=perimetre_arrondissement,
        deleguee_by=detr_enveloppe,
    )
    enveloppe.full_clean()
