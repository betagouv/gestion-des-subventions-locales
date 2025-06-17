import pytest

from gsl_core.tests.factories import (
    DepartementFactory,
)
from gsl_projet.models import CategorieDetr
from gsl_projet.tests.factories import (
    CategorieDetrFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def departement():
    return DepartementFactory()


@pytest.fixture
def some_categories_detr(departement):
    # not in filter because is_current=False
    CategorieDetrFactory.create_batch(2, departement=departement, is_current=False)
    # not in filter because wrong departement
    CategorieDetrFactory.create_batch(2, is_current=True)
    # expected in filters
    CategorieDetrFactory.create_batch(2, departement=departement, is_current=True)


def test_get_current_categories_for_departement(departement, some_categories_detr):
    assert CategorieDetr.objects.count() == 6

    qs = CategorieDetr.objects.current_for_departement(departement)

    assert qs.count() == 2
    first_result = qs.first()

    assert first_result.departement == departement
    assert first_result.is_current
