import pytest

from gsl.core.tests.factories import (
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.programmation.models import Enveloppe
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)


@pytest.fixture
def enveloppes_hierarchy():
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(parent=mother_enveloppe)
    grandchild_enveloppe = DetrEnveloppeFactory(parent=child_enveloppe)
    return mother_enveloppe, child_enveloppe, grandchild_enveloppe


@pytest.mark.django_db
def test_root_enveloppe_not_delegated(enveloppes_hierarchy):
    mother_enveloppe, _, _ = enveloppes_hierarchy
    assert mother_enveloppe.delegation_root == mother_enveloppe


@pytest.mark.django_db
def test_get_parent_enveloppe_delegated_once(enveloppes_hierarchy):
    mother_enveloppe, child_enveloppe, _ = enveloppes_hierarchy
    assert child_enveloppe.delegation_root == mother_enveloppe


@pytest.mark.django_db
def test_get_parent_enveloppe_delegated_multiple_times(enveloppes_hierarchy):
    mother_enveloppe, _, grandchild_enveloppe = enveloppes_hierarchy
    assert grandchild_enveloppe.delegation_root == mother_enveloppe


@pytest.fixture
def perimetres():
    arrondissement = PerimetreArrondissementFactory()
    departement = PerimetreDepartementalFactory(departement=arrondissement.departement)
    region = PerimetreRegionalFactory(region=arrondissement.region)
    return region, departement, arrondissement


@pytest.fixture
def delegated_enveloppes(perimetres):
    region, departement, arrondissement = perimetres
    regionale = DsilEnveloppeFactory(perimetre=region)
    departementale = DsilEnveloppeFactory(perimetre=departement, parent=regionale)
    arrondissementale = DsilEnveloppeFactory(
        perimetre=arrondissement, parent=departementale
    )
    return regionale, departementale, arrondissementale


@pytest.mark.django_db
def test_for_user_regional_sees_own_and_twice_delegated_enveloppes(
    perimetres, delegated_enveloppes
):
    region = perimetres[0]
    user = CollegueFactory(perimetre=region)
    DsilEnveloppeFactory()  # other region

    assert set(Enveloppe.objects.for_user(user)) == set(delegated_enveloppes)


@pytest.mark.django_db
def test_for_user_regional_sees_only_dsil_enveloppes(perimetres, delegated_enveloppes):
    region = perimetres[0]
    user = CollegueFactory(perimetre=region)
    # Bypasses the queryset create() guard forbidding regional DETR enveloppes
    DetrEnveloppeFactory.build(perimetre=region).save()

    assert set(Enveloppe.objects.for_user(user)) == set(delegated_enveloppes)


@pytest.mark.django_db
def test_for_user_departemental_sees_own_and_delegated_enveloppes(
    perimetres, delegated_enveloppes
):
    _, departementale, arrondissementale = delegated_enveloppes
    departement = perimetres[1]
    user = CollegueFactory(perimetre=departement)

    assert set(Enveloppe.objects.for_user(user)) == {
        departementale,
        arrondissementale,
    }


@pytest.mark.django_db
def test_for_user_arrondissement_sees_only_own_enveloppe(
    perimetres, delegated_enveloppes
):
    _, _, arrondissementale = delegated_enveloppes
    arrondissement = perimetres[2]
    user = CollegueFactory(perimetre=arrondissement)

    assert list(Enveloppe.objects.for_user(user)) == [arrondissementale]


@pytest.mark.django_db
def test_for_user_excludes_enveloppes_of_other_perimetres(delegated_enveloppes):
    user = CollegueFactory(perimetre=PerimetreRegionalFactory())

    assert not Enveloppe.objects.for_user(user).exists()


@pytest.mark.parametrize("is_staff, is_superuser", ((False, False), (True, True)))
@pytest.mark.django_db
def test_for_user_without_perimetre_sees_nothing(
    delegated_enveloppes, is_staff, is_superuser
):
    user = CollegueFactory(perimetre=None, is_staff=is_staff, is_superuser=is_superuser)

    assert not Enveloppe.objects.for_user(user).exists()
