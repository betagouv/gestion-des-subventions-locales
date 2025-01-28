import pytest

from ..models import (
    Demandeur,
    Projet,
)
from .factories import (
    DemandeurFactory,
    ProcessedProjetFactory,
    ProjetFactory,
    SubmittedProjetFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (DemandeurFactory, Demandeur),
    (ProjetFactory, Projet),
    (SubmittedProjetFactory, Projet),
    (ProcessedProjetFactory, Projet),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
