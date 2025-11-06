import json
from datetime import datetime
from pathlib import Path

import pytest
from django.utils import timezone

from gsl_core.tests.factories import (
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.importer.demarche import (
    extract_categories_operation_detr,
    get_or_create_demarche,
    guess_year_from_demarche,
    save_field_mappings,
    save_groupe_instructeurs,
)
from gsl_demarches_simplifiees.models import (
    Demarche,
    FieldMappingForComputer,
    FieldMappingForHuman,
    Profile,
)
from gsl_demarches_simplifiees.tests.factories import (
    DemarcheFactory,
    FieldMappingForComputerFactory,
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
        Path(__file__).parent.parent
        / "ds_fixtures"
        / "demarche_data_with_revision.json"
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
    assert isinstance(returned_demarche.active_revision_date, datetime)
    assert returned_demarche.active_revision_date.year == 2023
    assert returned_demarche.active_revision_date.month == 10
    assert returned_demarche.active_revision_date.day == 7
    assert returned_demarche.active_revision_id == "TEST_ID_MTYyNjE0"
    assert returned_demarche.raw_ds_data == demarche_data_without_dossier
    existing_demarche.refresh_from_db()
    assert existing_demarche.ds_title == "Titre de la démarche"
    assert existing_demarche.active_revision_id == "TEST_ID_MTYyNjE0"


def test_get_new_demarche_prefills_ds_fields(demarche_data_without_dossier):
    demarche = get_or_create_demarche(demarche_data_without_dossier)
    assert demarche.ds_id == "un-id-qui-nest-pas-un-vrai=="
    assert demarche.ds_number == 123456
    assert demarche.ds_title == "Titre de la démarche"
    assert demarche.ds_state == "brouillon"
    assert isinstance(demarche.active_revision_date, datetime)
    assert demarche.active_revision_date.year == 2023
    assert demarche.active_revision_date.month == 10
    assert demarche.active_revision_date.day == 7
    assert demarche.active_revision_id == "TEST_ID_MTYyNjE0"
    assert demarche.raw_ds_data == demarche_data_without_dossier


def test_get_or_create_demarche_with_no_active_revision():
    demarche_data = {
        "id": "un-id-qui-nest-pas-un-vrai==",
        "number": 123456,
        "title": "Titre de la démarche",
        "state": "brouillon",
        "dateCreation": "2023-10-07T14:47:24+02:00",
        "dateFermeture": None,
        "activeRevision": {
            "id": "UHJvY2VkdXJlUmV2aXNpb24tMjEzMjk4",
            "datePublication": None,
            "champDesciptors": [],
        },
        "groupeInstructeurs": [],
        "champs": [],
    }
    demarche = get_or_create_demarche(demarche_data)
    assert demarche.ds_id == "un-id-qui-nest-pas-un-vrai=="
    assert demarche.ds_number == 123456
    assert demarche.ds_title == "Titre de la démarche"
    assert demarche.ds_state == "brouillon"
    assert demarche.active_revision_date is None
    assert demarche.active_revision_id == "UHJvY2VkdXJlUmV2aXNpb24tMjEzMjk4"
    assert demarche.raw_ds_data == demarche_data


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

    assert FieldMappingForHuman.objects.count() == 4, (
        "4 human mappings should be created."
    )
    assert FieldMappingForHuman.objects.filter(label="Commentaire libre").exists()
    assert FieldMappingForHuman.objects.filter(
        label="Un champ qui ne porte pas ce nom-là dans Django"
    ).exists()

    assert (
        FieldMappingForComputer.objects.filter(
            ds_field_type="CheckboxChampDescriptor"
        ).count()
        == 4
    )
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
        == 1
    )
    assert FieldMappingForComputer.objects.count() == 18, (
        "18 computer mappings should have been created."
    )
    assert FieldMappingForComputer.objects.exclude(django_field="").count() == 14, (
        "Only 14 mappings should be associated with an existing field."
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


def test_categories_detr_are_created(demarche_data_without_dossier, demarche):
    # arrange
    FieldMappingForComputer.objects.create(
        demarche=demarche,
        django_field="demande_eligibilite_detr",
        ds_field_id="ID_DU_CHAMP_ELIGIBILTIE_DETR",
    )
    demarche.perimetre = PerimetreDepartementalFactory()
    demarche.ds_date_creation = timezone.datetime.fromisoformat(
        "2023-10-07T14:47:24+02:00"
    )

    # act
    extract_categories_operation_detr(demarche_data_without_dossier, demarche)

    # assert
    assert CategorieDetr.objects.count() == 2
    first_category = CategorieDetr.objects.first()
    assert first_category.rang == 1
    assert first_category.libelle == "Premier choix"
    assert first_category.annee == 2024
    assert first_category.departement == demarche.perimetre.departement


def test_no_error_if_cannot_guess_departement(demarche_data_without_dossier, demarche):
    # arrange
    FieldMappingForComputer.objects.create(
        demarche=demarche,
        django_field="demande_eligibilite_detr",
        ds_field_id="ID_DU_CHAMP_ELIGIBILTIE_DETR",
    )

    # act
    extract_categories_operation_detr(demarche_data_without_dossier, demarche)

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
    demarche = DemarcheFactory(
        ds_date_creation=timezone.datetime.fromisoformat(date_creation)
        if date_creation
        else None,
        active_revision_date=timezone.datetime.fromisoformat(date_revision)
        if date_revision
        else None,
    )
    # act
    year = guess_year_from_demarche(demarche)
    # assert
    assert year == expected_year


def _minimal_demarche_data_with_descriptors(descriptors):
    """Build minimal demarche data payload expected by save_field_mappings."""
    return {
        "id": "dummy-id",
        "number": 42,
        "title": "Titre",
        "state": "brouillon",
        "dateCreation": None,
        "dateFermeture": None,
        "activeRevision": {
            "id": "REV_ID",
            "datePublication": None,
            "champDescriptors": descriptors,
            "annotationDescriptors": [],
        },
        "groupeInstructeurs": [],
        "champs": [],
    }


def test_save_field_mappings_maps_by_verbose_name_direct_match(demarche):
    # Arrange: DS label equals Dossier.verbose_name for demandeur_arrondissement
    descriptors = [
        {
            "__typename": "TextChampDescriptor",
            "id": "FIELD_ID_ARR",
            "label": "Arrondissement du demandeur",
        }
    ]
    demarche_data = _minimal_demarche_data_with_descriptors(descriptors)

    # Act
    save_field_mappings(demarche_data, demarche)

    # Assert: a computer mapping exists and is mapped to the Django field
    mapping = FieldMappingForComputer.objects.get(
        demarche=demarche, ds_field_id="FIELD_ID_ARR"
    )
    assert mapping.django_field == "demandeur_arrondissement"


def test_save_field_mappings_maps_by_normalized_label_removing_parenthesis_suffix(
    demarche,
):
    # Arrange: DS label has a parenthetical suffix that should be stripped
    descriptors = [
        {
            "__typename": "TextChampDescriptor",
            "id": "FIELD_ID_ARR_PAREN",
            "label": "Arrondissement du demandeur (01 - Ain)",
        }
    ]
    demarche_data = _minimal_demarche_data_with_descriptors(descriptors)

    # Act
    save_field_mappings(demarche_data, demarche)

    # Assert: still maps to demandeur_arrondissement after normalization
    mapping = FieldMappingForComputer.objects.get(
        demarche=demarche, ds_field_id="FIELD_ID_ARR_PAREN"
    )
    assert mapping.django_field == "demandeur_arrondissement"
    # Human mapping should not be created when direct mapping succeeds via normalization
    assert (
        FieldMappingForHuman.objects.filter(
            label="Arrondissement du demandeur (01 - Ain)"
        ).count()
        == 0
    )


def test_save_field_mappings_maps_updates_existing_mapping(
    demarche,
):
    # Arrange: a mapping already exists
    mapping = FieldMappingForComputerFactory(
        demarche=demarche,
        ds_field_id="fixed_id",
        ds_field_label="a_label",
        ds_field_type="DropDownListChampDescriptor",
        django_field="a_django_field",
    )

    descriptors = [
        {
            "__typename": "TextChampDescriptor",
            "id": "fixed_id",
            "label": "Prénom du porteur de projet",
        }
    ]
    demarche_data = _minimal_demarche_data_with_descriptors(descriptors)

    # Act
    save_field_mappings(demarche_data, demarche)

    # Assert: still maps to demandeur_arrondissement after normalization
    mapping.refresh_from_db()
    assert mapping.ds_field_id == "fixed_id"
    assert mapping.ds_field_label == "Prénom du porteur de projet"
    assert mapping.ds_field_type == "TextChampDescriptor"
    assert mapping.django_field == "porteur_de_projet_prenom"
