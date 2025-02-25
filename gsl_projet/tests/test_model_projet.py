import pytest

from gsl_core.tests.factories import (
    AdresseFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..models import Projet

pytestmark = pytest.mark.django_db(transaction=True)


def test_create_projet_from_dossier():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    demandeur_commune = dossier.ds_demandeur.address.commune
    perimetre = PerimetreArrondissementFactory(
        arrondissement=demandeur_commune.arrondissement,
    )
    assert (
        dossier.ds_demandeur.address.commune.arrondissement == perimetre.arrondissement
    )
    assert dossier.ds_demandeur.address.commune.departement == perimetre.departement

    projet = Projet.get_or_create_from_ds_dossier(dossier)

    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address == dossier.projet_adresse
    assert projet.perimetre == perimetre

    other_projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert other_projet == projet
