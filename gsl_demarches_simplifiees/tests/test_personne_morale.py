import json
from pathlib import Path

import pytest

from gsl_core.models import Adresse
from gsl_demarches_simplifiees.models import (
    FormeJuridique,
    Naf,
    PersonneMorale,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def ds_dossier_data():
    with open(Path(__file__).parent / "ds_fixtures" / "dossier_data.json") as handle:
        return json.loads(handle.read())


@pytest.fixture
def ds_demandeur_data(ds_dossier_data):
    return ds_dossier_data.get("demandeur")


def test_create_personne_morale_commune(ds_demandeur_data):
    personne = PersonneMorale()
    personne.update_from_raw_ds_data(ds_demandeur_data)
    personne.save()
    assert isinstance(personne.address, Adresse)
    assert isinstance(personne.naf, Naf)
    assert isinstance(personne.forme_juridique, FormeJuridique)
