import pytest

from gsl_core.tests.factories import AdresseFactory, CollegueFactory
from gsl_demarches_simplifiees.models import Profile
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..models import Projet
from .factories import ProjetFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_user_can_see_a_projet_if_they_are_explicit_instructeur():
    user = CollegueFactory()
    dossier = DossierFactory()
    dossier.ds_demarche.ds_instructeurs.add(Profile.objects.create(ds_email=user.email))

    unrelated_projet = ProjetFactory()
    related_projet = ProjetFactory(dossier_ds=dossier)

    assert Projet.objects.count() == 2
    assert Projet.objects.for_user(user).count() == 1
    projets_for_user = Projet.objects.for_user(user).all()
    assert unrelated_projet not in projets_for_user
    assert related_projet in projets_for_user


def test_create_projet_from_dossier():
    dossier = DossierFactory(projet_adresse=AdresseFactory())
    projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert isinstance(projet, Projet)
    assert projet.address is not None
    assert projet.address.commune == dossier.projet_adresse.commune
    assert projet.address != dossier.projet_adresse

    other_projet = Projet.get_or_create_from_ds_dossier(dossier)
    assert other_projet == projet
