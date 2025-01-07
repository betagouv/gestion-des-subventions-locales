import pytest

from ..models import (
    Adresse,
    Arrondissement,
    Collegue,
    Commune,
    Departement,
    Perimetre,
    Region,
)
from .factories import (
    AdresseFactory,
    ArrondissementFactory,
    CollegueFactory,
    CommuneFactory,
    DepartementFactory,
    PerimetreFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db

test_data = (
    (CollegueFactory, Collegue),
    (RegionFactory, Region),
    (DepartementFactory, Departement),
    (ArrondissementFactory, Arrondissement),
    (CommuneFactory, Commune),
    (AdresseFactory, Adresse),
    (PerimetreFactory, Perimetre),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)
