import pytest
from django.db.utils import IntegrityError

from gsl_demarches_simplifiees.models import (
    CritereEligibiliteDetr,
)
from gsl_demarches_simplifiees.tests.factories import DemarcheFactory


@pytest.mark.django_db
def test_cannot_create_two_objects_with_equal_indexed_columns():
    libelle = "1. Premier choix"
    demarche = DemarcheFactory()
    revision = "xx"

    with pytest.raises(IntegrityError):
        CritereEligibiliteDetr.objects.create(
            label=libelle,
            demarche=demarche,
            demarche_revision=revision,
        )
        CritereEligibiliteDetr.objects.create(
            label=libelle,
            demarche=demarche,
            demarche_revision=revision,
        )


@pytest.mark.django_db
def test_cannot_create_two_objects_with_null_indexed_columns():
    libelle = "1. Premier choix"

    with pytest.raises(IntegrityError):
        CritereEligibiliteDetr.objects.create(
            label=libelle,
        )
        CritereEligibiliteDetr.objects.create(
            label=libelle,
        )


@pytest.mark.django_db
def test_can_create_several_objects_with_same_label():
    libelle = "1. Premier choix"

    first = CritereEligibiliteDetr.objects.create(
        demarche=DemarcheFactory(),
        label=libelle,
    )
    second = CritereEligibiliteDetr.objects.create(
        demarche=DemarcheFactory(),
        label=libelle,
    )

    assert first != second


@pytest.mark.django_db
def test_can_create_several_objects_with_different_revisions():
    libelle = "1. Premier choix"
    demarche = DemarcheFactory()
    first = CritereEligibiliteDetr.objects.create(
        label=libelle, demarche=demarche, demarche_revision="v1"
    )
    second = CritereEligibiliteDetr.objects.create(
        label=libelle, demarche=demarche, demarche_revision="v2"
    )

    assert first != second
