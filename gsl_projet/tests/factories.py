import factory

from gsl_core.tests.factories import (
    AdresseFactory,
    ArrondissementFactory,
    DepartementFactory,
)
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..models import Demandeur, Projet


class DemandeurFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Demandeur

    siret = factory.Sequence(lambda n: f"siret-{n}")
    name = factory.Faker("city", locale="fr_FR")

    address = factory.SubFactory(AdresseFactory)
    arrondissement = factory.SubFactory(ArrondissementFactory)
    departement = factory.SubFactory(DepartementFactory)


class ProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Projet

    demandeur = factory.SubFactory(DemandeurFactory)
    dossier_ds = factory.SubFactory(DossierFactory)

    address = factory.SubFactory(AdresseFactory)
    arrondissement = factory.SubFactory(ArrondissementFactory)
    departement = factory.SubFactory(DepartementFactory)
