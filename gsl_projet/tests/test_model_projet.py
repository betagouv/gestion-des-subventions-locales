import pytest

from gsl_core.models import Perimetre
from gsl_core.tests.factories import (
    AdresseFactory,
    ArrondissementFactory,
)
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..models import Projet
from .factories import DemandeurFactory, ProjetFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_create_projet_from_dossier():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address == dossier.projet_adresse

    other_projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert other_projet == projet


def test_filter_perimetre():
    arrondissement = ArrondissementFactory()
    demandeur_1 = DemandeurFactory(
        arrondissement=arrondissement, departement=arrondissement.departement
    )
    ProjetFactory(demandeur=demandeur_1)

    demandeur_2 = DemandeurFactory()
    ProjetFactory(demandeur=demandeur_2)

    perimetre = Perimetre.objects.create(
        region=demandeur_1.departement.region,
        arrondissement=demandeur_1.arrondissement,
        departement=demandeur_1.departement,
    )

    assert (
        Projet.objects.for_perimetre(None).count() == 2
    ), "Expect 2 projets for perimetre “None”"
    assert (
        Projet.objects.for_perimetre(perimetre).count() == 1
    ), "Expect 1 projet for perimetre “arrondissement”"
    assert (
        Projet.objects.for_perimetre(perimetre).first().demandeur.arrondissement
        == arrondissement
    )
    assert (
        Projet.objects.for_perimetre(perimetre).first().demandeur.departement
        == arrondissement.departement
    )
