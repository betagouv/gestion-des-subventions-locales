import json

import pytest

from ..models import Adresse, Commune, Region
from .factories import AdresseFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def complete_address_data():
    return json.loads("""{
    "label": "LE FROMAGER DE PIERRE BENITE CHEMIN DES MURIERS 69310 OULLINS-PIERRE-BENITE FRANCE",
    "type": "housenumber",
    "streetAddress": "CHEMIN DES MURIERS",
    "streetNumber": null,
    "streetName": "DES MURIERS",
    "postalCode": "69310",
    "cityName": "Oullins-Pierre-Bénite",
    "cityCode": "69149",
    "departmentName": "Rhône",
    "departmentCode": "69",
    "regionName": "Auvergne-Rhône-Alpes",
    "regionCode": "84"
  }
""")


@pytest.fixture
def simple_string_address():
    return "Rue Jean-Henri Fabre 12780 Saint-Léons"


def test_it_works_with_full_address_data(complete_address_data):
    adresse = Adresse()
    adresse.update_from_raw_ds_data(complete_address_data)
    assert adresse.label.startswith("LE FROMAGER")
    assert adresse.postal_code == "69310"
    assert adresse.commune.name == "Oullins-Pierre-Bénite"
    assert adresse.commune.insee_code == "69149"
    assert adresse.commune.departement.name == "Rhône"
    assert adresse.commune.departement.insee_code == "69"
    assert adresse.commune.departement.region.name == "Auvergne-Rhône-Alpes"
    assert adresse.commune.departement.region.insee_code == "84"
    adresse.save()

    another_adresse = Adresse()
    another_adresse.update_from_raw_ds_data(complete_address_data)
    another_adresse.save()

    assert another_adresse.commune == adresse.commune
    assert Commune.objects.count() == 1
    assert Region.objects.count() == 1


def test_it_works_with_a_simple_string(simple_string_address):
    adresse = Adresse()
    adresse.update_from_raw_ds_data(simple_string_address)
    adresse.save()

    assert adresse.label == simple_string_address


def test_an_adress_can_be_cloned():
    adresse = AdresseFactory()
    cloned = adresse.clone()
    cloned.save()
    assert adresse.pk is not None
    assert cloned.pk != adresse.pk
    assert cloned.commune == adresse.commune
