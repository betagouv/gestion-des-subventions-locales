import pytest
from django.test import Client

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
    ClientWithLoggedStaffUserFactory,
    ClientWithLoggedUserFactory,
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
    (PerimetreFactory, Perimetre),
)


@pytest.mark.parametrize("factory,expected_class", test_data)
def test_every_factory_can_be_called_twice(factory, expected_class):
    for _ in range(2):
        obj = factory()
        assert isinstance(obj, expected_class)


def test_client_factory():
    user = CollegueFactory()
    for _ in range(2):
        obj = ClientWithLoggedUserFactory(user)
        assert isinstance(obj, Client)


def test_staff_client_factory():
    for _ in range(2):
        obj = ClientWithLoggedStaffUserFactory()
        assert isinstance(obj, Client)
