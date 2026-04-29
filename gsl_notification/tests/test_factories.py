import pytest

from ..models import (
    Annexe,
    Arrete,
    LettreEtArreteSignes,
    LettreNotification,
    ModeleArrete,
    ModeleLettreNotification,
)
from .factories import (
    AnnexeFactory,
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    ModeleArreteFactory,
    ModeleLettreNotificationFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (ArreteFactory, Arrete),
    (LettreNotificationFactory, LettreNotification),
    (LettreEtArreteSignesFactory, LettreEtArreteSignes),
    (AnnexeFactory, Annexe),
    (ModeleLettreNotificationFactory, ModeleLettreNotification),
    (ModeleArreteFactory, ModeleArrete),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
