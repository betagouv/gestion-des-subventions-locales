import json
from pathlib import Path

import pytest

from gsl_demarches_simplifiees.importer.demarche import (
    save_field_mappings,
)
from gsl_demarches_simplifiees.models import Demarche

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
        Path(__file__) / ".." / "ds_fixtures" / "demarche_data_with_revision.json"
    ) as handle:
        return json.loads(handle.read())


def test_new_human_mapping_is_created_if_ds_label_is_unknown(demarche, demarche_data):
    save_field_mappings(demarche_data, demarche)
