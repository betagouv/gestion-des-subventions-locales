import json
from pathlib import Path

import pytest

from gsl_core.models import Adresse
from gsl_demarches_simplifiees.models import (
    FormeJuridique,
    Naf,
    PersonneMorale,
)

from ..factories import PersonneMoraleFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def ds_dossier_data():
    with open(
        Path(__file__).parent.parent / "ds_fixtures" / "dossier_data.json"
    ) as handle:
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


def test_siren_is_computed_from_siret_on_save():
    personne = PersonneMorale(siret="12345678900012")
    personne.save()
    assert personne.siren == "123456789"


def test_siren_is_recomputed_when_siret_changes():
    personne = PersonneMoraleFactory(siret="12345678900012")
    personne.siret = "98765432100045"
    personne.save()
    assert personne.siren == "987654321"


def test_distinct_by_siren():
    PersonneMoraleFactory(siret="12345678900012")
    PersonneMoraleFactory(siret="12345678900013")

    assert PersonneMorale.objects.distinct_by_siren().count() == 1
