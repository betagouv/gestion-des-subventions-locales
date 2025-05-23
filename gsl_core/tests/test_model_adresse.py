import json

import pytest

from ..models import Adresse, Commune, Region

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
def incomplete_address_data():
    return json.loads("""
    {"type": "housenumber",
    "label": "COMMUNE DE MEZERES\\r\\n\\r\\n\\r\\n\\r\\n\\r\\n43800 MEZERES\\r\\nFRANCE",
    "cityCode": "43134",
    "cityName": "Mézères",
    "postalCode": "43800",
    "regionCode": "84",
    "regionName": "Auvergne-Rhône-Alpes",
    "streetName": null,
    "streetNumber": null,
    "streetAddress": null,
    "departmentCode": "43",
    "departmentName": "Haute-Loire"}
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


def test_it_works_with_incomplete_address_data(incomplete_address_data):
    adresse = Adresse()
    adresse.update_from_raw_ds_data(incomplete_address_data)
    assert adresse.label.startswith("COMMUNE DE MEZERES")
    assert adresse.postal_code == "43800"
    assert adresse.commune.name == "Mézères"
    assert adresse.commune.insee_code == "43134"
    assert adresse.commune.departement.name == "Haute-Loire"
    assert adresse.commune.departement.insee_code == "43"
    assert adresse.commune.departement.region.name == "Auvergne-Rhône-Alpes"
    assert adresse.commune.departement.region.insee_code == "84"
    adresse.save()

    another_adresse = Adresse()
    another_adresse.update_from_raw_ds_data(incomplete_address_data)
    another_adresse.save()

    assert another_adresse.commune == adresse.commune
    assert Commune.objects.count() == 1
    assert Region.objects.count() == 1


def test_it_works_with_a_simple_string(simple_string_address):
    adresse = Adresse()
    adresse.update_from_raw_ds_data(simple_string_address)
    adresse.save()

    assert adresse.label == simple_string_address
