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
def dossier(dossier_ds_id, demarche):
    return Dossier(ds_id=dossier_ds_id, ds_demarche=demarche)


@pytest.fixture
def ds_dossier_data():
    with open(Path(__file__).parent / "ds_fixtures" / "dossier_data.json") as handle:
        return json.loads(handle.read())


def test_create_dossier_converter(ds_dossier_data, dossier):
    dossier_converter = DossierConverter(ds_dossier_data, dossier)
    assert dossier_converter.ds_field_ids
