import pytest

from gsl.core.models import BulkActionsJob

from ..models import Simulation, SimulationProjet
from .factories import (
    BulkStatusJobFactory,
    SimulationFactory,
    SimulationProjetFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (SimulationFactory, Simulation),
    (SimulationProjetFactory, SimulationProjet),
    (BulkStatusJobFactory, BulkActionsJob),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
