import pytest

from gsl_core.models import Departement
from gsl_core.tests.factories import (
    AdresseFactory,
    ArrondissementFactory,
    CollegueFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
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

    perimetre = PerimetreArrondissementFactory(
        arrondissement=arrondissement,
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


@pytest.fixture
def departement() -> Departement:
    return DepartementFactory()


@pytest.fixture
def projets(departement) -> list[Projet]:
    projet_with_departement = ProjetFactory(demandeur__departement=departement)
    projet_without_departement = ProjetFactory()

    return [projet_with_departement, projet_without_departement]


def test_for_staff_user_without_perimetre(projets):
    staff_user = CollegueFactory(is_staff=True, perimetre=None)
    assert Projet.objects.for_user(staff_user).count() == 2


def test_for_super_user_without_perimetre(projets):
    super_user = CollegueFactory(is_superuser=True, perimetre=None)
    assert Projet.objects.for_user(super_user).count() == 2


def test_for_normal_user_without_perimetre(projets):
    user = CollegueFactory(perimetre=None)
    assert Projet.objects.for_user(user).count() == 0


def test_for_staff_user_with_perimetre(departement, projets):
    staff_user_with_perimetre = CollegueFactory(
        is_staff=True, perimetre=PerimetreDepartementalFactory(departement=departement)
    )
    assert Projet.objects.for_user(staff_user_with_perimetre).count() == 1
    assert Projet.objects.for_user(staff_user_with_perimetre).get() == projets[0]


def test_for_super_user_with_perimetre(departement, projets):
    super_user_with_perimetre = CollegueFactory(
        is_superuser=True,
        perimetre=PerimetreDepartementalFactory(departement=departement),
    )
    assert Projet.objects.for_user(super_user_with_perimetre).count() == 1
    assert Projet.objects.for_user(super_user_with_perimetre).get() == projets[0]


def test_for_normal_user_with_perimetre(departement, projets):
    user_with_perimetre = CollegueFactory(
        perimetre=PerimetreDepartementalFactory(departement=departement)
    )
    assert Projet.objects.for_user(user_with_perimetre).count() == 1
    assert Projet.objects.for_user(user_with_perimetre).get() == projets[0]
