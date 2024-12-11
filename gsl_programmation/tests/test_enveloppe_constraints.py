from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from gsl_core.tests.factories import (
    ArrondissementFactory,
    DepartementFactory,
    RegionFactory,
)

from ..models import Enveloppe

pytestmark = pytest.mark.django_db


@pytest.fixture
def arrondissement():
    return ArrondissementFactory()


@pytest.fixture
def region():
    return RegionFactory()


@pytest.fixture
def departement():
    return DepartementFactory()


def test_any_enveloppe_must_have_only_one_perimeter(arrondissement, departement):
    with pytest.raises(ValidationError):
        enveloppe = Enveloppe(
            type=Enveloppe.TYPE_DETR,
            montant=Decimal("123.00"),
            annee=2025,
            perimetre_arrondissement=arrondissement,
            perimetre_departement=departement,
        )
        enveloppe.full_clean()


def test_dsil_not_delegated_must_have_regional_perimeter(arrondissement):
    with pytest.raises(ValidationError):
        enveloppe = Enveloppe(
            type=Enveloppe.TYPE_DSIL,
            montant=Decimal("123.00"),
            annee=2025,
            perimetre_arrondissement=arrondissement,
        )
        enveloppe.full_clean()


def test_detr_not_delegated_must_have_departemental_perimeter(arrondissement):
    with pytest.raises(ValidationError):
        enveloppe = Enveloppe(
            type=Enveloppe.TYPE_DETR,
            montant=Decimal("123.00"),
            annee=2025,
            perimetre_arrondissement=arrondissement,
        )
        enveloppe.full_clean()


def test_correct_dsil_non_delegated(region):
    enveloppe = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_region=region,
    )
    enveloppe.full_clean()


@pytest.fixture
def dsil_enveloppe(arrondissement):
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_region=arrondissement.departement.region,
    )


def test_correct_dsil_delegated_to_departement(dsil_enveloppe, arrondissement):
    enveloppe_departement = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_departement=arrondissement.departement,
        deleguee_by=dsil_enveloppe,
    )
    enveloppe_departement.full_clean()


def test_correct_dsil_delegated_to_arrondissement(dsil_enveloppe, arrondissement):
    enveloppe_departement = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_departement=arrondissement.departement,
        deleguee_by=dsil_enveloppe,
    )
    enveloppe_departement.full_clean()
    enveloppe_departement.save()
    enveloppe_arrondissement = Enveloppe(
        type=Enveloppe.TYPE_DSIL,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_arrondissement=arrondissement,
        deleguee_by=enveloppe_departement,
    )
    enveloppe_arrondissement.full_clean()


def test_correct_detr_non_delegated(departement):
    enveloppe = Enveloppe(
        type=Enveloppe.TYPE_DETR,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_departement=departement,
    )
    enveloppe.full_clean()


@pytest.fixture
def detr_enveloppe(arrondissement):
    return Enveloppe.objects.create(
        type=Enveloppe.TYPE_DETR,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_departement=arrondissement.departement,
    )


def test_correct_detr_delegated(detr_enveloppe, arrondissement):
    enveloppe = Enveloppe(
        type=Enveloppe.TYPE_DETR,
        montant=Decimal("12345.00"),
        annee=2032,
        perimetre_arrondissement=arrondissement,
        deleguee_by=detr_enveloppe,
    )
    enveloppe.full_clean()
