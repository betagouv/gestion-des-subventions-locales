import factory

from ..models import Adresse, Arrondissement, Collegue, Commune, Departement, Region


class CollegueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Collegue

    username = factory.Faker("user_name")
    email = factory.Faker("email")
    is_staff = False
    is_active = True


class RegionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Region

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("word", locale="fr_FR")


class DepartementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Departement

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("word", locale="fr_FR")
    region = factory.SubFactory(RegionFactory)


class ArrondissementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Arrondissement

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("city", locale="fr_FR")
    departement = factory.SubFactory(DepartementFactory)


class CommuneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Commune

    insee_code = factory.Sequence(lambda n: f"{n}")
    name = factory.Faker("city", locale="fr_FR")
    departement = factory.SubFactory(DepartementFactory)


class AdresseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Adresse

    label = factory.Faker("address", locale="fr_FR")
    postal_code = factory.Faker("postcode", locale="fr_FR")
    commune = factory.SubFactory(CommuneFactory)
    street_address = factory.Faker("street_address", locale="fr_FR")
