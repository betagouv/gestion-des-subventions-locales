import datetime
import json
from pathlib import Path

import pytest

from gsl_core.models import Adresse
from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.models import (
    CritereEligibiliteDetr,
    Demarche,
    Dossier,
    DossierData,
    FieldMappingForComputer,
    PersonneMorale,
)
from gsl_demarches_simplifiees.tests.factories import DemarcheFactory

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("celery_session_app"),
    pytest.mark.usefixtures("celery_session_worker"),
]


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
    return Dossier.objects.create(
        ds_id=dossier_ds_id,
        ds_demarche_number=demarche.ds_number,
        ds_number=dossier_ds_number,
        ds_data=DossierData.objects.create(
            ds_demarche=demarche,
        ),
    )


@pytest.fixture
def ds_dossier_data():
    with open(
        Path(__file__).parent / ".." / "ds_fixtures" / "dossier_data.json"
    ) as handle:
        return json.loads(handle.read())


@pytest.fixture
def dossier_converter(ds_dossier_data, dossier):
    return DossierConverter(ds_dossier_data, dossier)


def test_init_dossier_converter(ds_dossier_data, dossier):
    FieldMappingForComputer.objects.create(
        ds_field_id="TEST_ID_un_champ_hors_annotation",
        django_field=Dossier._MAPPED_CHAMPS_FIELDS[0].name,
        demarche=dossier.ds_data.ds_demarche,
    )
    FieldMappingForComputer.objects.create(
        ds_field_id="TEST_ID_un_champ_annotation",
        django_field=Dossier._MAPPED_ANNOTATIONS_FIELDS[0].name,
        demarche=dossier.ds_data.ds_demarche,
    )
    dossier_converter = DossierConverter(ds_dossier_data, dossier)

    assert "TEST_ID_un_champ_hors_annotation" in dossier_converter.ds_fields_by_id
    assert "TEST_ID_un_champ_annotation" in dossier_converter.ds_fields_by_id
    assert len(dossier_converter.ds_fields_by_id) == (
        len(ds_dossier_data["champs"]) + len(ds_dossier_data["annotations"])
    )
    assert (
        dossier_converter.ds_id_to_django_field["TEST_ID_un_champ_hors_annotation"]
        == Dossier._MAPPED_CHAMPS_FIELDS[0]
    )
    assert (
        dossier_converter.ds_id_to_django_field["TEST_ID_un_champ_annotation"]
        == Dossier._MAPPED_ANNOTATIONS_FIELDS[0]
    )


def test_non_mapped_fields_are_imported(dossier_converter: DossierConverter):
    dossier_converter.fill_unmapped_fields()
    assert isinstance(dossier_converter.dossier.ds_demandeur, PersonneMorale)


def test_demandeur_is_properly_found_if_already_existing(
    dossier_converter, ds_dossier_data
):
    existing_demandeur = PersonneMorale.objects.create(
        siret=ds_dossier_data["demandeur"]["siret"]
    )
    assert PersonneMorale.objects.count() == 1
    assert dossier_converter.dossier.ds_demandeur is None

    dossier_converter.fill_unmapped_fields()

    assert PersonneMorale.objects.count() == 1
    assert isinstance(dossier_converter.dossier.ds_demandeur, PersonneMorale)
    assert dossier_converter.dossier.ds_demandeur.siret == existing_demandeur.siret


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
    (
        {
            "id": "TEST_ID_MzI3Njk1NA==",
            "label": "Département du porteur de projet",
            "prefilled": False,
            "updatedAt": "2025-09-29T16:28:56+02:00",
            "__typename": "LinkedDropDownListChamp",
            "stringValue": "57 - Moselle / 579 - Metz",
            "primaryValue": "57 - Moselle",
            "secondaryValue": "579 - Metz",
            "champDescriptorId": "TEST_ID_I3Njk1NA==",
        },
        "579 - Metz",
    ),
    (
        {
            "id": "TEST_ID_zNTY1MA==",
            "label": "Si oui, précisez le niveau de priorité de ce dossier.",
            "prefilled": False,
            "updatedAt": "2024-02-20T23:03:28+01:00",
            "__typename": "IntegerNumberChamp",
            "stringValue": "2",
            "integerNumber": "2",
            "champDescriptorId": "Q2hhbXAtMzMzNTY1MA==",
        },
        2,
    ),
    (
        {
            "id": "TEST_ID_k0NTU5OA==",
            "champDescriptorId": "TEST_ID_jk0NTU5OA==",
            "__typename": "SiretChamp",
            "label": "Identification du maître d'ouvrage",
            "stringValue": "69850088100033",
            "updatedAt": "2024-10-17T21:12:12+02:00",
            "prefilled": False,
            "etablissement": {},
            "entreprise": {},
            "association": None,
        },
        "69850088100033",
    ),
    (
        {
            "id": "TEST_ID_yMDUwMA==",
            "champDescriptorId": "TEST_ID_AyMDUwMA==",
            "__typename": "AddressChamp",
            "label": "Adresse principale du projet",
            "stringValue": "Rue Jean-Henri Fabre 12780 Saint-Léons",
            "updatedAt": "2024-11-06T15:55:12+01:00",
            "prefilled": False,
            "address": None,
            "commune": None,
            "departement": None,
        },
        "Rue Jean-Henri Fabre 12780 Saint-Léons",
    ),
    (
        {
            "id": "TEST_ID_AyMDUwMA==",
            "champDescriptorId": "TEST_ID_MDUwMA==",
            "__typename": "AddressChamp",
            "label": "Adresse principale du projet",
            "stringValue": "2 Rue des Ecoles 67240 Schirrhein",
            "updatedAt": "2024-10-16T10:07:10+02:00",
            "prefilled": False,
            "address": {
                "label": "2 Rue des Ecoles 67240 Schirrhein",
                "type": "housenumber",
                "streetAddress": "2 Rue des Ecoles",
                "streetNumber": "2",
                "streetName": "Rue des Ecoles",
                "postalCode": "67240",
                "cityName": "Schirrhein",
                "cityCode": "67449",
                "departmentName": "Bas-Rhin",
                "departmentCode": "67",
                "regionName": "Grand Est",
                "regionCode": "44",
            },
            "commune": {"name": "Schirrhein", "code": "67449", "postalCode": "67240"},
            "departement": {"name": "Bas-Rhin", "code": "67"},
        },
        {
            "label": "2 Rue des Ecoles 67240 Schirrhein",
            "type": "housenumber",
            "streetAddress": "2 Rue des Ecoles",
            "streetNumber": "2",
            "streetName": "Rue des Ecoles",
            "postalCode": "67240",
            "cityName": "Schirrhein",
            "cityCode": "67449",
            "departmentName": "Bas-Rhin",
            "departmentCode": "67",
            "regionName": "Grand Est",
            "regionCode": "44",
        },
    ),
)


def idfn(fixture_value):
    if isinstance(fixture_value, dict):
        return fixture_value.get("__typename", "dict")


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


def test_inject_manytomany_value(dossier_converter, dossier):
    dossier_converter.inject_into_field(
        dossier,
        Dossier._meta.get_field("projet_zonage"),
        [
            "Territoires d'industrie (TI)",
            "Territoires Engagées pour la Nature (TEN)",
            "Site patrimonial remarquable (SPR)",
        ],
    )
    dossier.save()
    assert len(dossier.projet_zonage.all()) == 3


def test_inject_string_into_manytomany_value(dossier_converter, dossier):
    dossier_converter.inject_into_field(
        dossier,
        Dossier._meta.get_field("projet_zonage"),
        "Territoires d'industrie (TI)",
    )
    dossier.save()
    assert len(dossier.projet_zonage.all()) == 1


def test_inject_correct_category_detr_value_with_several_demarches(
    dossier_converter, dossier
):
    libelle = "1. Valeur du premier choix"
    demarche_revision = ""
    other_critere_detr = CritereEligibiliteDetr.objects.create(
        demarche=DemarcheFactory(ds_title="Démarche qui n'a rien à voir"),
        label=libelle,
        demarche_revision="tata",
    )
    good_critere_detr = CritereEligibiliteDetr.objects.create(
        demarche=dossier.ds_data.ds_demarche,
        label=libelle,
        demarche_revision=demarche_revision,
    )
    dossier_converter.ds_demarche_revision = demarche_revision
    dossier_converter.inject_into_field(
        dossier,
        Dossier._meta.get_field("demande_eligibilite_detr"),
        libelle,
    )
    dossier.save()
    dossier_critere = dossier.demande_eligibilite_detr.first()
    assert dossier_critere == good_critere_detr
    assert dossier_critere != other_critere_detr


def test_inject_address_value(dossier_converter, dossier):
    dossier_converter.inject_into_field(
        dossier,
        Dossier._meta.get_field("projet_adresse"),
        {
            "label": "2 Rue des Ecoles 67240 Schirrhein",
            "type": "housenumber",
            "streetAddress": "2 Rue des Ecoles",
            "streetNumber": "2",
            "streetName": "Rue des Ecoles",
            "postalCode": "67240",
            "cityName": "Schirrhein",
            "cityCode": "67449",
            "departmentName": "Bas-Rhin",
            "departmentCode": "67",
            "regionName": "Grand Est",
            "regionCode": "44",
        },
    )
    dossier.save()
    assert Adresse.objects.count() == 1
    assert dossier.projet_adresse.label.startswith("2 Rue des Ecoles")
    assert dossier.projet_adresse.commune.name == "Schirrhein"
    assert dossier.projet_adresse.commune.insee_code == "67449"
