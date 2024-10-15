import json
from pathlib import Path

import pytest

from gsl_demarches_simplifiees.importer.demarche import (
    save_field_mappings,
)
from gsl_demarches_simplifiees.models import (
    Demarche,
    FieldMappingForComputer,
    FieldMappingForHuman,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def demarche():
    return Demarche.objects.create(
        ds_id="lidentifiantdsdelademarche",
        ds_number=123456,
        ds_title="Titre de la démarche",
        ds_state=Demarche.STATE_PUBLIEE,
    )


@pytest.fixture
def demarche_data_without_dossier():
    with open(
        Path(__file__).parent / "ds_fixtures" / "demarche_data_with_revision.json"
    ) as handle:
        return json.loads(handle.read())


def test_new_human_mapping_is_created_if_ds_label_is_unknown(
    demarche, demarche_data_without_dossier
):
    assert FieldMappingForHuman.objects.count() == 0
    assert FieldMappingForComputer.objects.count() == 0

    save_field_mappings(demarche_data_without_dossier, demarche)

    assert FieldMappingForHuman.objects.count() == 2
    assert FieldMappingForHuman.objects.filter(label="Commentaire libre").exists()
    assert FieldMappingForHuman.objects.filter(
        label="Un champ qui ne porte pas ce nom-là dans Django"
    ).exists()
    assert FieldMappingForComputer.objects.count() == 4


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
