import pytest

from gsl_programmation.tests.factories import DetrEnveloppeFactory


@pytest.fixture
def enveloppes_hierarchy():
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    grandchild_enveloppe = DetrEnveloppeFactory(deleguee_by=child_enveloppe)
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
