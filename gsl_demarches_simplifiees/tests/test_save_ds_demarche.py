import json
from pathlib import Path

import pytest

from gsl_core.tests.factories import DepartementFactory
from gsl_demarches_simplifiees.importer.demarche import (
    extract_ds_choice_libelles,
    get_or_create_demarche,
    guess_year_from_demarche_data,
    save_field_mappings,
    save_groupe_instructeurs,
)
from gsl_demarches_simplifiees.models import (
    Demarche,
    Dossier,
    FieldMappingForComputer,
    FieldMappingForHuman,
    Profile,
)
from gsl_projet.models import CategorieDetr

pytestmark = pytest.mark.django_db


@pytest.fixture
def demarche():
    return Demarche.objects.create(
        ds_id="lidentifiantdsdelademarche",
        ds_number=123456,
        ds_title="Titre de la démarche pour le Bas-Rhin",
        ds_state=Demarche.STATE_PUBLIEE,
    )


@pytest.fixture
def demarche_data_without_dossier():
    with open(
        Path(__file__).parent / "ds_fixtures" / "demarche_data_with_revision.json"
    ) as handle:
        return json.loads(handle.read())


def test_get_existing_demarche_updates_ds_fields(demarche_data_without_dossier):
    existing_demarche = Demarche.objects.create(
        ds_id="un-id-qui-nest-pas-un-vrai==",
        ds_number=666666,
        ds_title="Le titre qui va changer",
        ds_state=Demarche.STATE_PUBLIEE,
    )
    returned_demarche = get_or_create_demarche(demarche_data_without_dossier)
    assert existing_demarche.ds_id == returned_demarche.ds_id
    assert existing_demarche.pk == returned_demarche.pk
    assert returned_demarche.ds_title == "Titre de la démarche"
    assert returned_demarche.ds_number == 123456
    assert returned_demarche.ds_state == "brouillon"
    assert returned_demarche.raw_ds_data == demarche_data_without_dossier


def test_get_new_demarche_prefills_ds_fields(demarche_data_without_dossier):
    demarche = get_or_create_demarche(demarche_data_without_dossier)
    assert demarche.ds_id == "un-id-qui-nest-pas-un-vrai=="
    assert demarche.ds_number == 123456
    assert demarche.ds_title == "Titre de la démarche"
    assert demarche.ds_state == "brouillon"
    assert demarche.raw_ds_data == demarche_data_without_dossier


def test_save_groupe_instructeurs(demarche, demarche_data_without_dossier):
    save_groupe_instructeurs(demarche_data_without_dossier, demarche)
    assert Profile.objects.count() == 2
    assert Profile.objects.filter(
        ds_id="TEST_ID_ldXItMTIzNTcx", ds_email="hubert.lingot@example.com"
    ).exists()


def test_save_groupe_instructeurs_if_already_exists(
    demarche, demarche_data_without_dossier
):
    assert Profile.objects.create(
        ds_id="TEST_ID_ldXItMTIzNTcx", ds_email="hubert.lingot@example.com"
    )
    save_groupe_instructeurs(demarche_data_without_dossier, demarche)
    assert Profile.objects.count() == 2


def test_new_human_mapping_is_created_if_ds_label_is_unknown(
    demarche, demarche_data_without_dossier
):
    assert FieldMappingForHuman.objects.count() == 0
    assert FieldMappingForComputer.objects.count() == 0

    save_field_mappings(demarche_data_without_dossier, demarche)

    assert FieldMappingForHuman.objects.count() == 2, (
        "Two human mappings should be created."
    )
    assert FieldMappingForHuman.objects.filter(label="Commentaire libre").exists()
    assert FieldMappingForHuman.objects.filter(
        label="Un champ qui ne porte pas ce nom-là dans Django"
    ).exists()

    assert (
        FieldMappingForComputer.objects.filter(
            ds_field_type="DecimalNumberChampDescriptor"
        ).count()
        == 4
    )
    assert (
        FieldMappingForComputer.objects.filter(
            ds_field_type="DropDownListChampDescriptor"
        ).count()
        == 2
    )
    assert (
        FieldMappingForComputer.objects.filter(
            ds_field_type="SiretChampDescriptor"
        ).count()
        == 1
    )
    assert (
        FieldMappingForComputer.objects.filter(
            ds_field_type="TextChampDescriptor"
        ).count()
        == 2
    )
    assert (
        FieldMappingForComputer.objects.filter(
            ds_field_type="YesNoChampDescriptor"
        ).count()
        == 1
    )
    assert (
        FieldMappingForComputer.objects.filter(
            ds_field_type="MultipleDropDownListChampDescriptor"
        ).count()
        == 2
    )
    assert FieldMappingForComputer.objects.count() == 14, (
        "14 computer mappings should have been created."
    )
    assert FieldMappingForComputer.objects.exclude(django_field="").count() == 12, (
        "Only 12 mappings should be associated with an existing field."
    )


def test_existing_human_mapping_is_used_if_possible(
    demarche, demarche_data_without_dossier
):
    FieldMappingForHuman.objects.create(
        label="Un champ qui ne porte pas ce nom-là dans Django",
        django_field="projet_contractualisation_autre",
    )
    assert FieldMappingForComputer.objects.count() == 0

    save_field_mappings(demarche_data_without_dossier, demarche)

    assert FieldMappingForComputer.objects.count() > 1
    assert FieldMappingForComputer.objects.filter(
        ds_field_label="Un champ qui ne porte pas ce nom-là dans Django",
        ds_field_id="TEST_ID_MjkzNDM2MA==",
        django_field="projet_contractualisation_autre",
        ds_field_type="TextChampDescriptor",
    ).exists()


def test_ds_field_id_is_used_even_if_ds_label_changes(
    demarche_data_without_dossier, demarche
):
    FieldMappingForComputer.objects.create(
        ds_field_label="Un champ qui a changé de nom dans DS",
        ds_field_id="TEST_ID_MjkzNDM2MA==",
        django_field="projet_contractualisation_autre",
        demarche=demarche,
        ds_field_type="TextChampDescriptor",
    )
    assert FieldMappingForHuman.objects.count() == 0

    save_field_mappings(demarche_data_without_dossier, demarche)

    assert (
        FieldMappingForHuman.objects.filter(
            label="Un champ qui ne porte pas ce nom-là dans Django"
        ).count()
        == 0
    )


def test_choice_labels_are_created(demarche_data_without_dossier, demarche):
    # arrange
    FieldMappingForComputer.objects.create(
        demarche=demarche,
        django_field="porteur_de_projet_nature",
        ds_field_id="ID_CHAMP_NATURE_PORTEUR_PROJET",
    )  # foreignkey in Django, DropDownListChampDescriptor in DS
    FieldMappingForComputer.objects.create(
        demarche=demarche,
        django_field="projet_zonage",
        ds_field_id="ID_CHAMP_ZONAGE_SPECIFIQUE",
    )  # ManyToManyField in Django, MultipleDropDownListChampDescriptor in DS

    # act
    extract_ds_choice_libelles(demarche_data_without_dossier, demarche)

    # assert
    assert Dossier._meta.get_field("projet_zonage").related_model.objects.count() == 11
    assert (
        Dossier._meta.get_field(
            "porteur_de_projet_nature"
        ).related_model.objects.count()
        == 4
    )


def test_categories_detr_are_created(demarche_data_without_dossier, demarche):
    # arrange
    departement = DepartementFactory(name="Bas-Rhin")  # to fit demarche.name
    FieldMappingForComputer.objects.create(
        demarche=demarche,
        django_field="demande_eligibilite_detr",
        ds_field_id="ID_DU_CHAMP_ELIGIBILTIE_DETR",
    )

    # act
    extract_ds_choice_libelles(demarche_data_without_dossier, demarche)

    # assert
    assert CategorieDetr.objects.count() == 2
    first_category = CategorieDetr.objects.first()
    assert first_category.tri == 0
    assert first_category.libelle == "Premier choix"
    assert first_category.annee == 2025
    assert first_category.departement == departement


def test_no_error_if_cannot_guess_departement(demarche_data_without_dossier, demarche):
    # arrange
    FieldMappingForComputer.objects.create(
        demarche=demarche,
        django_field="demande_eligibilite_detr",
        ds_field_id="ID_DU_CHAMP_ELIGIBILTIE_DETR",
    )

    # act
    extract_ds_choice_libelles(demarche_data_without_dossier, demarche)

    # assert
    assert CategorieDetr.objects.count() == 0


@pytest.mark.parametrize(
    "date_revision, date_creation, expected_year, comment",
    (
        (
            "2023-10-07T14:47:24+02:00",
            "2022-06-07T14:47:24+02:00",
            2024,
            "Révision après septembre => année N+1",
        ),
        (
            "2023-07-07T14:47:24+02:00",
            "2022-10-07T14:47:24+02:00",
            2023,
            "Révision avant septembre => année N",
        ),
        (
            None,
            "2022-10-07T14:47:24+02:00",
            2023,
            "Pas de révision, création après septembre => année N+1",
        ),
        (
            None,
            "2022-04-07T14:47:24+02:00",
            2022,
            "Pas de révision, création avant septembre => année N",
        ),
    ),
)
def test_guess_year_from_demarche_data(
    demarche_data_without_dossier, date_revision, date_creation, expected_year, comment
):
    # arrange
    demarche_data_without_dossier["activeRevision"]["datePublication"] = date_revision
    demarche_data_without_dossier["dateCreation"] = date_creation
    # act
    year = guess_year_from_demarche_data(demarche_data_without_dossier)
    # assert
    assert year == expected_year
