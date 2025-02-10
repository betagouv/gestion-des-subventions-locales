import pytest

from ..models import Enveloppe
from .factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (DetrEnveloppeFactory, Enveloppe),
    (DsilEnveloppeFactory, Enveloppe),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
