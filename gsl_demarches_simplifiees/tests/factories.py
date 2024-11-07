import factory

from ..models import Demarche, Dossier


class DemarcheFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Demarche

    ds_id = factory.Sequence(lambda n: f"demarche-{n}")
    ds_number = factory.Faker("random_int", min=1000000, max=9999999)
    ds_title = "Titre de la démarche"
    ds_state = Demarche.STATE_PUBLIEE


class DossierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dossier

    ds_demarche = factory.SubFactory(DemarcheFactory)
    ds_id = factory.Sequence(lambda n: f"dossier-{n}")
    ds_number = factory.Faker("random_int", min=1000000, max=9999999)
    ds_state = Dossier.STATE_ACCEPTE
