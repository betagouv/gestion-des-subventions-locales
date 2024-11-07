import pytest

from gsl_core.tests.factories import CollegueFactory
from gsl_demarches_simplifiees.models import Profile
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..models import Projet
from .factories import ProjetFactory

pytestmark = pytest.mark.django_db


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
