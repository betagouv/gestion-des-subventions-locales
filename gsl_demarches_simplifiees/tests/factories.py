import factory

from gsl_core.tests.factories import AdresseFactory

from ..models import Demarche, Dossier, PersonneMorale


class DemarcheFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Demarche

    ds_id = factory.Sequence(lambda n: f"demarche-{n}")
    ds_number = factory.Faker("random_int", min=1000000, max=9999999)
    ds_title = "Titre de la démarche"
    ds_state = Demarche.STATE_PUBLIEE


class PersonneMoraleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PersonneMorale

    siret = factory.Sequence(lambda n: f"personnemorale-{n}")
    raison_sociale = factory.Faker("word", locale="fr_FR")
    address = factory.SubFactory(AdresseFactory)


class DossierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dossier

    ds_demarche = factory.SubFactory(DemarcheFactory)
    ds_id = factory.Sequence(lambda n: f"dossier-{n}")
    ds_number = factory.Faker("random_int", min=1000000, max=9999999)
    ds_state = Dossier.STATE_ACCEPTE
    ds_demandeur = factory.SubFactory(PersonneMoraleFactory)
