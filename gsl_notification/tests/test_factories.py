import pytest

from ..models import (
    Arrete,
    ArreteSigne,
)
from .factories import (
    ArreteFactory,
    ArreteSigneFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (ArreteFactory, Arrete),
    (ArreteSigneFactory, ArreteSigne),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
