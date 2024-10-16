import datetime
import json
from pathlib import Path

import pytest

from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.models import (
    Demarche,
    Dossier,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def demarche_number():
    return 123456


@pytest.fixture
def demarche_ds_id():
    return "lidentifiantdsdelademarche"


@pytest.fixture
def demarche(demarche_number, demarche_ds_id):
    return Demarche.objects.create(
        ds_id=demarche_ds_id,
        ds_number=demarche_number,
        ds_title="Titre de la démarche",
        ds_state=Demarche.STATE_PUBLIEE,
    )


@pytest.fixture
def dossier_ds_id():
    return "l-id-du-dossier"


@pytest.fixture
def dossier_ds_number():
    return 445566


@pytest.fixture
def dossier(dossier_ds_id, demarche, dossier_ds_number):
    return Dossier(
        ds_id=dossier_ds_id, ds_demarche=demarche, ds_number=dossier_ds_number
    )


@pytest.fixture
def ds_dossier_data():
    with open(Path(__file__).parent / "ds_fixtures" / "dossier_data.json") as handle:
        return json.loads(handle.read())


@pytest.fixture
def dossier_converter(ds_dossier_data, dossier):
    return DossierConverter(ds_dossier_data, dossier)


def test_create_dossier_converter(ds_dossier_data, dossier):
    dossier_converter = DossierConverter(ds_dossier_data, dossier)
    assert dossier_converter.ds_field_ids


extract_field_test_data = (
    (
        {
            "id": "TEST_ID_MzMzNjEwMA==",
            "champDescriptorId": "TEST_ID_MzMzNjEwMA==",
            "__typename": "CheckboxChamp",
            "label": "Projet concourant à la transition écologique au sens budget vert",
            "stringValue": "false",
            "updatedAt": "2024-10-16T10:05:33+02:00",
            "prefilled": False,
            "checked": False,
        },
        False,
    ),
    (
        {
            "id": "TEST_ID_MzQ2NzY5OQ==",
            "champDescriptorId": "TEST_ID_MzQ2NzY5OQ==",
            "__typename": "CheckboxChamp",
            "label": "Le projet concourt-il aux enjeux de la transition écologique ?",
            "stringValue": "true",
            "updatedAt": "2024-10-16T10:07:58+02:00",
            "prefilled": False,
            "checked": True,
        },
        True,
    ),
    (
        {
            "id": "TEST_ID_MzQ2NzcwMA==",
            "champDescriptorId": "TEST_ID_MzQ2NzcwMA==",
            "__typename": "TextChamp",
            "label": "Justifier en quelques mots.",
            "stringValue": "lorem ipsum dolor sit amet",
            "updatedAt": "2024-10-16T10:08:14+02:00",
            "prefilled": False,
        },
        "lorem ipsum dolor sit amet",
    ),
    (
        {
            "id": "TEST_ID_Mjk0NTcxMg==",
            "champDescriptorId": "TEST_ID_Mjk0NTcxMg==",
            "__typename": "DateChamp",
            "label": "Date de commencement de l'opération",
            "stringValue": "15 janvier 2025",
            "updatedAt": "2024-10-16T10:08:21+02:00",
            "prefilled": False,
            "date": "2025-01-15",
        },
        datetime.date(2025, 1, 15),
    ),
    (
        {
            "id": "TEST_ID_Mjk0NzQzNw==",
            "champDescriptorId": "TEST_ID_Mjk0NzQzNw==",
            "__typename": "DecimalNumberChamp",
            "label": "Coût total de l'opération (en euros HT)",
            "stringValue": "256888.00",
            "updatedAt": "2024-10-16T10:08:46+02:00",
            "prefilled": False,
            "decimalNumber": 256888,
        },
        256888,
    ),
    (
        {
            "id": "TEST_ID_NDU4MzEwOA==",
            "champDescriptorId": "TEST_ID_NDU4MzEwOA==",
            "__typename": "DecimalNumberChamp",
            "label": "Je demande ce montant de subventions",
            "stringValue": "2349.90",
            "updatedAt": "2024-10-16T10:09:15+02:00",
            "prefilled": False,
            "decimalNumber": 2349.9,
        },
        2349.9,
    ),
    (
        {
            "id": "TEST_ID_MzUwOTY5OQ==",
            "champDescriptorId": "TEST_ID_MzUwOTY5OQ==",
            "__typename": "MultipleDropDownListChamp",
            "label": "Eligibilité de l'opération à la DETR",
            "stringValue": "Premier choix, Deuxième choix",
            "updatedAt": "2024-10-16T10:09:07+02:00",
            "prefilled": False,
            "values": ["Premier choix", "Deuxième choix"],
        },
        ["Premier choix", "Deuxième choix"],
    ),
)


def idfn(fixture_value):
    if isinstance(fixture_value, dict):
        return fixture_value["__typename"]


@pytest.mark.parametrize("input,expected", extract_field_test_data, ids=idfn)
def test_extract_field_data(input, expected, dossier_converter):
    assert dossier_converter.extract_ds_data(input) == expected


def test_inject_scalar_value(dossier_converter, dossier):
    dossier_converter.inject_into_field(
        dossier, Dossier._meta.get_field("date_achevement"), datetime.date(2025, 2, 2)
    )
    dossier.save()
    assert dossier.date_achevement == datetime.date(2025, 2, 2)


def test_inject_foreign_key_value(dossier_converter, dossier):
    dossier_converter.inject_into_field(
        dossier,
        Dossier._meta.get_field("porteur_de_projet_arrondissement"),
        "67 - Bas-Rhin - arrondissement de Haguenau-Wissembourg",
    )
    dossier.save()
    assert (
        dossier.porteur_de_projet_arrondissement.label
        == "67 - Bas-Rhin - arrondissement de Haguenau-Wissembourg"
    )
