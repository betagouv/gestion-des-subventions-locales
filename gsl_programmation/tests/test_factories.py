import pytest

from ..models import Enveloppe, ProgrammationProjet
from .factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    EnveloppeFactory,
    ProgrammationProjetFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (EnveloppeFactory, Enveloppe),
    (DetrEnveloppeFactory, Enveloppe),
    (DsilEnveloppeFactory, Enveloppe),
    (ProgrammationProjetFactory, ProgrammationProjet),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
