import json
from pathlib import Path

import pytest

from gsl_demarches_simplifiees.importer.dossier import get_or_create_dossier
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


def test_create_new_dossier(demarche_number, demarche, dossier_ds_id):
    dossier = get_or_create_dossier(dossier_ds_id, demarche_number)
    assert dossier.ds_id == dossier_ds_id
    assert dossier.ds_demarche.ds_number == demarche_number


def test_get_existing_dossier(
    demarche_number, demarche, dossier_ds_id, dossier_ds_number
):
    existing_dossier = Dossier.objects.create(
        ds_id=dossier_ds_id,
        ds_demarche=demarche,
        ds_number=dossier_ds_number,
        ds_state=Dossier.STATE_EN_INSTRUCTION,
    )
    retrieved_dossier = get_or_create_dossier(dossier_ds_id, demarche_number)
    assert existing_dossier.pk == retrieved_dossier.pk


@pytest.fixture
def demarche_data_without_dossier():
    with open(
        Path(__file__).parent / "ds_fixtures" / "demarche_data_with_revision.json"
    ) as handle:
        return json.loads(handle.read())
