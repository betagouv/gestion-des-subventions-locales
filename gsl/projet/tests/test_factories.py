import pytest

from gsl_core.tests.factories import DepartementFactory

from ..models import CategorieDetr, DotationProjet, Projet, ProjetNote
from .factories import (
    CategorieDetrFactory,
    DotationProjetFactory,
    ProcessedProjetFactory,
    ProjetFactory,
    ProjetNoteFactory,
    SubmittedProjetFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (ProjetFactory, Projet),
    (SubmittedProjetFactory, Projet),
    (ProcessedProjetFactory, Projet),
    (DotationProjetFactory, DotationProjet),
    (CategorieDetrFactory, CategorieDetr),
    (ProjetNoteFactory, ProjetNote),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)


def test_category_detr_factory_can_be_called_twice_with_same_parameters():
    annee = 2025
    rang = 7
    departement = DepartementFactory()
    assert CategorieDetr.objects.count() == 0

    for _ in range(2):
        category = CategorieDetrFactory(rang=rang, annee=annee, departement=departement)

    assert category.rang == rang
    assert category.annee == 2025
    assert category.departement == departement

    assert CategorieDetr.objects.count() == 1
