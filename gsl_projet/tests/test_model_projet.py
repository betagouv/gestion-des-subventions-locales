import pytest

from gsl_core.models import Arrondissement
from gsl_core.tests.factories import (
    AdresseFactory,
)
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..models import Projet

pytestmark = pytest.mark.django_db(transaction=True)


def test_create_projet_from_dossier():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address == dossier.projet_adresse

    assert projet.demandeur is not None
    assert isinstance(projet.demandeur.arrondissement, Arrondissement)
    other_projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert other_projet == projet
