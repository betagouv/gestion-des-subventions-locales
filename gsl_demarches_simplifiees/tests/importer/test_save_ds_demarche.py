import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from django.utils import timezone

from gsl_core.tests.factories import DepartementFactory
from gsl_demarches_simplifiees.importer.demarche import (
    _get_departement_from_field_mapping,
    _save_categorie_detr_from_field,
    save_categories_dsil,
    save_demarche_from_ds,
    save_field_mappings,
    save_groupe_instructeurs,
    update_or_create_demarche,
)
from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    CategorieDsil,
    Demarche,
    FieldMapping,
    Profile,
)
from gsl_demarches_simplifiees.tests.factories import (
    CategorieDetrFactory,
    DemarcheFactory,
    FieldMappingFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def demarche():
    return DemarcheFactory(
        ds_id="UHJvY2VkdXJlLTEzMTAxNg==",
        ds_number=131016,
        ds_title="Titre de la démarche pour le Bas-Rhin",
        ds_state=Demarche.STATE_PUBLIEE,
        active_revision_id="UHJvY2VkdXJlUmV2aXNpb24tMjM1OTE5",
    )


@pytest.fixture
def demarche_data_without_dossier():
    with open(
        Path(__file__).parent.parent
        / "ds_fixtures"
        / "demarche_data_with_revision.json"
    ) as handle:
        return json.loads(handle.read())


def test_save_demarche_from_ds_with_refresh_only_if_demarche_has_been_updated(
    demarche_data_without_dossier,
    demarche,
):
    original_updated_at = demarche.updated_at

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_demarche"
    ) as get_demarche:
        get_demarche.return_value = {
            "data": {
                "demarche": demarche_data_without_dossier,
            },
        }

        save_demarche_from_ds(
            demarche.ds_number,
            refresh_only_if_demarche_has_been_updated=True,
        )

    demarche.refresh_from_db()

    assert demarche.active_revision_id == "UHJvY2VkdXJlUmV2aXNpb24tMjM1OTE5"
    assert demarche.updated_at == original_updated_at


# Mocked because save_categories_detr needs Departements to be created
@patch("gsl_demarches_simplifiees.importer.demarche.save_categories_detr")
def test_save_demarche_from_ds_even_if_active_revision_id_is_the_same(
    _save_categories_detr,
    demarche_data_without_dossier,
    demarche,
):
    original_updated_at = demarche.updated_at

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_demarche"
    ) as get_demarche:
        get_demarche.return_value = {
            "data": {
                "demarche": demarche_data_without_dossier,
            },
        }

        save_demarche_from_ds(
            demarche.ds_number,
            refresh_only_if_demarche_has_been_updated=False,
        )

    demarche.refresh_from_db()

    assert demarche.active_revision_id == "UHJvY2VkdXJlUmV2aXNpb24tMjM1OTE5"
    assert demarche.updated_at > original_updated_at


def test_get_existing_demarche_updates_ds_fields(demarche_data_without_dossier):
    existing_demarche = Demarche.objects.create(
        ds_id="UHJvY2VkdXJlLTEzMTAxNg==",
        ds_number=666666,
        ds_title="Le titre qui va changer",
        ds_state=Demarche.STATE_PUBLIEE,
    )
    returned_demarche = update_or_create_demarche(demarche_data_without_dossier)
    assert existing_demarche.ds_id == returned_demarche.ds_id
    assert existing_demarche.pk == returned_demarche.pk
    assert (
        returned_demarche.ds_title
        == " Demande de subvention au titre de la DETR et de la DSIL - TEST TURGOT 2"
    )
    assert returned_demarche.ds_number == 131016
    assert returned_demarche.ds_state == "publiee"
    assert isinstance(returned_demarche.active_revision_date, datetime)
    assert returned_demarche.active_revision_date.year == 2025
    assert returned_demarche.active_revision_date.month == 12
    assert returned_demarche.active_revision_date.day == 19
    assert returned_demarche.active_revision_id == "UHJvY2VkdXJlUmV2aXNpb24tMjM1OTE5"
    assert returned_demarche.raw_ds_data == demarche_data_without_dossier
    existing_demarche.refresh_from_db()
    assert (
        existing_demarche.ds_title
        == " Demande de subvention au titre de la DETR et de la DSIL - TEST TURGOT 2"
    )

    assert existing_demarche.active_revision_id == "UHJvY2VkdXJlUmV2aXNpb24tMjM1OTE5"


def test_get_new_demarche_prefills_ds_fields(demarche_data_without_dossier):
    demarche = update_or_create_demarche(demarche_data_without_dossier)
    assert demarche.ds_id == "UHJvY2VkdXJlLTEzMTAxNg=="
    assert demarche.ds_number == 131016
    assert (
        demarche.ds_title
        == " Demande de subvention au titre de la DETR et de la DSIL - TEST TURGOT 2"
    )
    assert demarche.ds_state == "publiee"
    assert isinstance(demarche.active_revision_date, datetime)
    assert demarche.active_revision_date.year == 2025
    assert demarche.active_revision_date.month == 12
    assert demarche.active_revision_date.day == 19
    assert demarche.active_revision_id == "UHJvY2VkdXJlUmV2aXNpb24tMjM1OTE5"
    assert demarche.raw_ds_data == demarche_data_without_dossier


def test_update_or_create_demarche_with_no_active_revision():
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
    demarche = update_or_create_demarche(demarche_data)
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


def test_computer_mappings_are_created(demarche, demarche_data_without_dossier):
    assert FieldMapping.objects.count() == 0

    save_field_mappings(demarche_data_without_dossier, demarche)

    assert (
        FieldMapping.objects.filter(ds_field_type="CheckboxChampDescriptor").count()
        == 15
    )
    assert (
        FieldMapping.objects.filter(
            ds_field_type="DecimalNumberChampDescriptor"
        ).count()
        == 6
    )
    assert (
        FieldMapping.objects.filter(ds_field_type="DropDownListChampDescriptor").count()
        == 171
    )
    assert (
        FieldMapping.objects.filter(ds_field_type="SiretChampDescriptor").count() == 1
    )
    assert (
        FieldMapping.objects.filter(ds_field_type="TextChampDescriptor").count() == 18
    )
    assert (
        FieldMapping.objects.filter(ds_field_type="YesNoChampDescriptor").count() == 8
    )
    assert (
        FieldMapping.objects.filter(
            ds_field_type="MultipleDropDownListChampDescriptor"
        ).count()
        == 7
    )
    assert (
        FieldMapping.objects.filter(ds_field_type="DossierLinkChampDescriptor").count()
        == 4
    )
    assert FieldMapping.objects.count() == 294
    assert FieldMapping.objects.exclude(django_field="").count() == 242

    demande_categorie_detr_mappings = FieldMapping.objects.filter(
        django_field="demande_categorie_detr"
    ).count()
    assert demande_categorie_detr_mappings == 100

    porteur_de_projet_arrondissement_mappings = FieldMapping.objects.filter(
        django_field="porteur_de_projet_arrondissement"
    ).count()
    assert porteur_de_projet_arrondissement_mappings == 98


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
    # Arrange: DN label equals Dossier.verbose_name for demandeur_arrondissement
    descriptors = [
        {
            "__typename": "TextChampDescriptor",
            "id": "FIELD_ID_ARR",
            "label": "Nom du porteur de projet",
        }
    ]
    demarche_data = _minimal_demarche_data_with_descriptors(descriptors)

    # Act
    save_field_mappings(demarche_data, demarche)

    # Assert: a computer mapping exists and is mapped to the Django field
    mapping = FieldMapping.objects.get(demarche=demarche, ds_field_id="FIELD_ID_ARR")
    assert mapping.django_field == "porteur_de_projet_nom"


def test_save_field_mappings_maps_updates_existing_mapping(
    demarche,
):
    # Arrange: a mapping already exists
    mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_id="fixed_id",
        ds_field_label="a_label",
        ds_field_type="DropDownListChampDescriptor",
        django_field="a_django_field",
    )
    original_updated_at = mapping.updated_at

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
    assert mapping.updated_at > original_updated_at


def test_save_field_mappings_dont_update_existing_mapping_if_ds_label_and_type_are_the_same(
    demarche,
):
    # Arrange: a mapping already exists
    mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_id="fixed_id",
        ds_field_label="Prénom du porteur de projet",
        ds_field_type="TextChampDescriptor",
        django_field="porteur_de_projet_prenom",
    )
    original_updated_at = mapping.updated_at

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

    # Assert: updated_at is the same as created_at
    mapping.refresh_from_db()
    assert mapping.updated_at == original_updated_at


def test_save_categories_dsil_creates_new_categories(demarche):
    # Arrange
    field_id = "CATEGORY_FIELD_ID"
    FieldMappingFactory(
        demarche=demarche,
        django_field="demande_categorie_dsil",
        ds_field_id=field_id,
    )
    demarche_data = {
        "activeRevision": {
            "id": "REV_ID",
            "champDescriptors": [
                {
                    "id": field_id,
                    "label": "Catégorie DSIL",
                    "options": ["Catégorie 1", "Catégorie 2", "Catégorie 3"],
                }
            ],
        }
    }

    # Act
    save_categories_dsil(demarche_data, demarche)

    # Assert
    categories = CategorieDsil.objects.filter(demarche=demarche, active=True).order_by(
        "rank"
    )
    assert categories.count() == 3
    assert categories[0].label == "Catégorie 1"
    assert categories[0].rank == 1
    assert categories[0].active is True
    assert categories[1].label == "Catégorie 2"
    assert categories[1].rank == 2
    assert categories[1].active is True
    assert categories[2].label == "Catégorie 3"
    assert categories[2].rank == 3
    assert categories[2].active is True


def test_save_categories_dsil_updates_existing_categories(demarche):
    # Arrange
    field_id = "CATEGORY_FIELD_ID"
    FieldMappingFactory(
        demarche=demarche,
        django_field="demande_categorie_dsil",
        ds_field_id=field_id,
    )
    # Create existing category
    existing_category = CategorieDsil.objects.create(
        demarche=demarche,
        label="Catégorie 1",
        rank=1,
        active=True,
    )
    demarche_data = {
        "activeRevision": {
            "id": "REV_ID",
            "champDescriptors": [
                {
                    "id": field_id,
                    "label": "Catégorie DSIL",
                    "options": ["Catégorie 1", "Catégorie 2"],
                }
            ],
        }
    }

    # Act
    save_categories_dsil(demarche_data, demarche)

    # Assert
    existing_category.refresh_from_db()
    assert existing_category.active is True
    assert existing_category.rank == 1
    categories = CategorieDsil.objects.filter(demarche=demarche, active=True).order_by(
        "rank"
    )
    assert categories.count() == 2
    assert categories[0].id == existing_category.id
    assert categories[1].label == "Catégorie 2"
    assert categories[1].rank == 2


def test_save_categories_dsil_deactivates_old_categories(demarche):
    # Arrange
    field_id = "CATEGORY_FIELD_ID"
    FieldMappingFactory(
        demarche=demarche,
        django_field="demande_categorie_dsil",
        ds_field_id=field_id,
    )
    # Create old categories
    old_category_1 = CategorieDsil.objects.create(
        demarche=demarche,
        label="Ancienne Catégorie 1",
        rank=1,
        active=True,
    )
    old_category_2 = CategorieDsil.objects.create(
        demarche=demarche,
        label="Ancienne Catégorie 2",
        rank=2,
        active=True,
    )
    demarche_data = {
        "activeRevision": {
            "id": "REV_ID",
            "champDescriptors": [
                {
                    "id": field_id,
                    "label": "Catégorie DSIL",
                    "options": ["Nouvelle Catégorie"],
                }
            ],
        }
    }

    # Act
    save_categories_dsil(demarche_data, demarche)

    # Assert
    old_category_1.refresh_from_db()
    old_category_2.refresh_from_db()
    assert old_category_1.active is False
    assert old_category_1.deactivated_at is not None
    assert old_category_2.active is False
    assert old_category_2.deactivated_at is not None

    active_categories = CategorieDsil.objects.filter(demarche=demarche, active=True)
    assert active_categories.count() == 1
    assert active_categories[0].label == "Nouvelle Catégorie"


def test_save_categories_dsil_handles_empty_options(demarche):
    # Arrange
    field_id = "CATEGORY_FIELD_ID"
    FieldMappingFactory(
        demarche=demarche,
        django_field="demande_categorie_dsil",
        ds_field_id=field_id,
    )
    # Create existing category
    old_category = CategorieDsil.objects.create(
        demarche=demarche,
        label="Ancienne Catégorie",
        rank=1,
        active=True,
    )
    demarche_data = {
        "activeRevision": {
            "id": "REV_ID",
            "champDescriptors": [
                {
                    "id": field_id,
                    "label": "Catégorie DSIL",
                    "options": [],
                }
            ],
        }
    }

    # Act
    save_categories_dsil(demarche_data, demarche)

    # Assert
    old_category.refresh_from_db()
    assert old_category.active is False
    assert old_category.deactivated_at is not None
    assert CategorieDsil.objects.filter(demarche=demarche, active=True).count() == 0


def test_save_categories_dsil_raises_error_if_mapping_not_found(demarche):
    # Arrange - no mapping created
    demarche_data = {
        "activeRevision": {
            "id": "REV_ID",
            "champDescriptors": [
                {
                    "id": "SOME_FIELD_ID",
                    "label": "Catégorie DSIL",
                    "options": ["Catégorie 1"],
                }
            ],
        }
    }

    # Act & Assert
    with pytest.raises(FieldMapping.DoesNotExist):
        save_categories_dsil(demarche_data, demarche)


def test_save_categories_dsil_handles_field_not_in_descriptors(demarche):
    # Arrange
    field_id = "CATEGORY_FIELD_ID"
    FieldMappingFactory(
        demarche=demarche,
        django_field="demande_categorie_dsil",
        ds_field_id=field_id,
    )
    demarche_data = {
        "activeRevision": {
            "id": "REV_ID",
            "champDescriptors": [
                {
                    "id": "OTHER_FIELD_ID",
                    "label": "Autre champ",
                    "options": ["Option 1"],
                }
            ],
        }
    }

    # Act
    save_categories_dsil(demarche_data, demarche)

    # Assert - no categories should be created, existing ones should be deactivated
    assert CategorieDsil.objects.filter(demarche=demarche, active=True).count() == 0


def test_save_categories_dsil_preserves_inactive_categories(demarche):
    # Arrange
    field_id = "CATEGORY_FIELD_ID"
    FieldMappingFactory(
        demarche=demarche,
        django_field="demande_categorie_dsil",
        ds_field_id=field_id,
    )
    # Create an inactive category (should remain inactive)
    inactive_category = CategorieDsil.objects.create(
        demarche=demarche,
        label="Inactive Category",
        rank=1,
        active=False,
        deactivated_at=timezone.now(),
    )
    demarche_data = {
        "activeRevision": {
            "id": "REV_ID",
            "champDescriptors": [
                {
                    "id": field_id,
                    "label": "Catégorie DSIL",
                    "options": ["Nouvelle Catégorie"],
                }
            ],
        }
    }

    # Act
    save_categories_dsil(demarche_data, demarche)

    # Assert
    inactive_category.refresh_from_db()
    assert inactive_category.active is False
    # The inactive category should remain unchanged
    assert CategorieDsil.objects.filter(demarche=demarche, active=False).count() == 1
    assert CategorieDsil.objects.filter(demarche=demarche, active=True).count() == 1


# --- _get_departement_from_field_mapping ---


@pytest.mark.parametrize(
    "ds_field_label,insee_code",
    [
        ("Catégories prioritaires (87 - Haute-Vienne)", "87"),
        ("Catégories prioritaires (91 - Essonne)", "91"),
        ("Catégories prioritaires (988 - Nouvelle-Calédonie)", "988"),
        ("Catégories prioritaires (2A - Corse-du-Sud)", "2A"),
        ("Catégories prioritaires (07 - Ardèche)", "07"),
    ],
)
def test_get_departement_from_field_mapping_returns_departement_when_label_matches(
    demarche, ds_field_label, insee_code
):
    DepartementFactory(insee_code=insee_code, name="Test")
    mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label=ds_field_label,
    )

    result = _get_departement_from_field_mapping(mapping)

    assert result is not None
    assert result.insee_code == insee_code


def test_get_departement_from_field_mapping_returns_none_when_label_does_not_match(
    demarche,
):
    mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Some other field without (code - name) pattern",
    )

    result = _get_departement_from_field_mapping(mapping)

    assert result is None


def test_get_departement_from_field_mapping_returns_none_when_departement_does_not_exist(
    demarche,
):
    mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (99 - Inexistante)",
    )
    # No Departement with insee_code=99 in DB

    result = _get_departement_from_field_mapping(mapping)

    assert result is None


def test_get_departement_from_field_mapping_returns_none_for_empty_label(demarche):
    mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="",
    )

    result = _get_departement_from_field_mapping(mapping)

    assert result is None


# --- _save_categorie_detr_from_field ---


def test_save_categorie_detr_from_field_creates_categories(
    demarche,
):
    ds_departement = DepartementFactory(insee_code="87", name="Haute-Vienne")

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (87 - Haute-Vienne)",
    )
    field = {
        "label": "Catégories prioritaires (87 - Haute-Vienne)",
        "options": ["Catégorie A", "Catégorie B", "Catégorie C"],
    }

    _save_categorie_detr_from_field(field, field_mapping, demarche)

    categories = CategorieDetr.objects.filter(
        demarche=demarche, departement=ds_departement, active=True
    ).order_by("rank")
    assert categories.count() == 3
    assert categories[0].label == "Catégorie A"
    assert categories[0].rank == 1
    assert categories[0].parent_label == ""
    assert categories[1].label == "Catégorie B"
    assert categories[1].rank == 2
    assert categories[2].label == "Catégorie C"
    assert categories[2].rank == 3


def test_save_categorie_detr_from_field_sets_parent_label_for_options_after_dash_line(
    demarche,
):
    ds_departement = DepartementFactory(insee_code="91", name="Essonne")

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (91 - Essonne)",
    )
    field = {
        "label": "Catégories prioritaires (91 - Essonne)",
        "options": [
            "Catégorie 1",
            "--Sous-groupe",
            "Catégorie 2",
            "Catégorie 3",
        ],
    }

    _save_categorie_detr_from_field(field, field_mapping, demarche)

    categories = CategorieDetr.objects.filter(
        demarche=demarche, departement=ds_departement, active=True
    ).order_by("rank")
    assert categories.count() == 3
    assert categories[0].label == "Catégorie 1"
    assert categories[0].rank == 1
    assert categories[0].parent_label == ""
    assert categories[1].label == "Catégorie 2"
    assert categories[1].rank == 3  # 2 is the "--Sous-groupe" option index
    assert categories[1].parent_label == "Sous-groupe"
    assert categories[2].label == "Catégorie 3"
    assert categories[2].rank == 4
    assert categories[2].parent_label == "Sous-groupe"


def test_save_categorie_detr_from_field_updates_existing_category(demarche):
    ds_departement = DepartementFactory(insee_code="07", name="Ardèche")

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (07 - Ardèche)",
    )
    existing = CategorieDetrFactory(
        demarche=demarche,
        departement=ds_departement,
        label="Catégorie existante",
        rank=1,
        active=True,
    )
    field = {
        "label": "Catégories prioritaires (07 - Ardèche)",
        "options": ["Catégorie existante", "Nouvelle catégorie"],
    }

    _save_categorie_detr_from_field(field, field_mapping, demarche)

    categories = CategorieDetr.objects.filter(
        demarche=demarche, departement=ds_departement, active=True
    ).order_by("rank")
    assert categories.count() == 2
    existing.refresh_from_db()
    assert existing.label == "Catégorie existante"
    assert existing.rank == 1
    assert existing.active is True
    new_one = categories.get(label="Nouvelle catégorie")
    assert new_one.rank == 2


def test_save_categorie_detr_from_field_deactivates_removed_options(demarche):
    departement = DepartementFactory(insee_code="2A", name="Corse-du-Sud")

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (2A - Corse-du-Sud)",
    )
    old_category = CategorieDetrFactory(
        demarche=demarche,
        departement=departement,
        label="Ancienne catégorie",
        rank=1,
        active=True,
    )
    field = {
        "label": "Catégories prioritaires (2A - Corse-du-Sud)",
        "options": ["Seule catégorie restante"],
    }

    _save_categorie_detr_from_field(field, field_mapping, demarche)

    old_category.refresh_from_db()
    assert old_category.active is False
    assert old_category.deactivated_at is not None
    remaining = CategorieDetr.objects.get(
        demarche=demarche, departement=departement, label="Seule catégorie restante"
    )
    assert remaining.active is True


@patch(
    "gsl_demarches_simplifiees.importer.demarche._get_departement_from_field_mapping"
)
def test_save_categorie_detr_from_field_does_nothing_when_no_departement(
    mock_get_departement, demarche
):
    mock_get_departement.return_value = None

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (99 - Inexistante)",
    )
    field = {
        "label": "Catégories prioritaires (99 - Inexistante)",
        "options": ["Quelque chose"],
    }

    _save_categorie_detr_from_field(field, field_mapping, demarche)

    mock_get_departement.assert_called_once_with(field_mapping)
    assert CategorieDetr.objects.filter(demarche=demarche).count() == 0


def test_save_categorie_detr_with_other_ranks(
    demarche,
):
    # Arrange
    ds_departement = DepartementFactory(insee_code="87", name="Haute-Vienne")
    for rank, label in enumerate(["Catégorie A", "Catégorie B", "Catégorie C"], 1):
        CategorieDetrFactory(
            demarche=demarche,
            departement=ds_departement,
            label=label,
            rank=rank,
            active=True,
        )

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (87 - Haute-Vienne)",
    )
    field = {
        "label": "Catégories prioritaires (87 - Haute-Vienne)",
        "options": ["Catégorie B", "Catégorie C", "Catégorie A"],
    }

    # Act
    _save_categorie_detr_from_field(field, field_mapping, demarche)

    # Assert
    categories = CategorieDetr.objects.filter(
        demarche=demarche, departement=ds_departement
    ).order_by("rank")
    assert categories.count() == 3
    assert categories[0].label == "Catégorie B"
    assert categories[0].rank == 1
    assert categories[0].parent_label == ""
    assert categories[1].label == "Catégorie C"
    assert categories[1].rank == 2
    assert categories[2].label == "Catégorie A"
    assert categories[2].rank == 3


def test_save_categorie_detr_with_other_ranks_and_parent_label(
    demarche,
):
    # Arrange
    ds_departement = DepartementFactory(insee_code="87", name="Haute-Vienne")
    for rank, label in enumerate(["Catégorie A", "Catégorie B", "Catégorie C"], 1):
        CategorieDetrFactory(
            demarche=demarche,
            departement=ds_departement,
            label=label,
            rank=rank,
            active=True,
        )

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (87 - Haute-Vienne)",
    )
    field = {
        "label": "Catégories prioritaires (87 - Haute-Vienne)",
        "options": [
            "--Parent 1--",
            "Catégorie A",
            "--Parent 2--",
            "Catégorie B",
            "--Parent 3--",
            "Catégorie C",
        ],
    }

    # Act
    _save_categorie_detr_from_field(field, field_mapping, demarche)

    # Assert
    categories = CategorieDetr.objects.filter(
        demarche=demarche, departement=ds_departement
    ).order_by("rank")
    assert categories.count() == 3
    assert categories[0].label == "Catégorie A"
    assert categories[0].rank == 2
    assert categories[0].parent_label == "Parent 1"
    assert categories[1].label == "Catégorie B"
    assert categories[1].rank == 4
    assert categories[1].parent_label == "Parent 2"
    assert categories[2].label == "Catégorie C"
    assert categories[2].rank == 6
    assert categories[2].parent_label == "Parent 3"


def test_save_categorie_detr_with_other_ranks_and_parent_label_and_deactivated_at(
    demarche,
):
    # Arrange
    ds_departement = DepartementFactory(insee_code="87", name="Haute-Vienne")
    CategorieDetrFactory(
        demarche=demarche,
        departement=ds_departement,
        label="Catégorie A",
        rank=10,
        active=False,
        parent_label="Parent 1",
        deactivated_at=timezone.now(),
    )

    field_mapping = FieldMappingFactory(
        demarche=demarche,
        ds_field_label="Catégories prioritaires (87 - Haute-Vienne)",
    )
    field = {
        "label": "Catégories prioritaires (87 - Haute-Vienne)",
        "options": [
            "Catégorie A",
            "Catégorie B",
        ],
    }

    # Act
    _save_categorie_detr_from_field(field, field_mapping, demarche)

    # Assert
    categories = CategorieDetr.objects.filter(
        demarche=demarche, departement=ds_departement
    ).order_by("rank")
    assert categories.count() == 2
    assert categories[0].label == "Catégorie A"
    assert categories[0].rank == 1
    assert categories[0].parent_label == ""
    assert categories[0].active is True
    assert categories[0].deactivated_at is None
    assert categories[1].label == "Catégorie B"
    assert categories[1].rank == 2
    assert categories[1].parent_label == ""
    assert categories[1].active is True
    assert categories[1].deactivated_at is None
