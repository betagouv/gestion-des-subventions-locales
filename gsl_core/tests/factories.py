import factory
from django.test import RequestFactory

from ..models import (
    Adresse,
    Arrondissement,
    Collegue,
    Commune,
    Departement,
    Perimetre,
    Region,
)


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
    arrondissement = factory.SubFactory(ArrondissementFactory)
    departement = factory.LazyAttribute(lambda obj: obj.arrondissement.departement)


class AdresseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Adresse

    label = factory.Faker("address", locale="fr_FR")
    postal_code = factory.Faker("postcode", locale="fr_FR")
    commune = factory.SubFactory(CommuneFactory)
    street_address = factory.Faker("street_address", locale="fr_FR")


class PerimetreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Perimetre

    arrondissement = None
    departement = factory.SubFactory(DepartementFactory)
    region = factory.LazyAttribute(lambda obj: obj.departement.region)


class PerimetreDepartementalFactory(PerimetreFactory):
    pass


class PerimetreRegionalFactory(PerimetreFactory):
    departement = None
    region = factory.SubFactory(RegionFactory)


class PerimetreArrondissementFactory(PerimetreFactory):
    arrondissement = factory.SubFactory(ArrondissementFactory)
    departement = factory.LazyAttribute(lambda obj: obj.arrondissement.departement)
    region = factory.LazyAttribute(lambda obj: obj.arrondissement.departement.region)


class CollegueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Collegue

    username = factory.Faker("user_name")
    email = factory.Faker("email")
    is_staff = False
    is_active = True
    perimetre = factory.SubFactory(PerimetreFactory)


class RequestFactory(RequestFactory):
    user = factory.SubFactory(CollegueFactory)

    def __init__(self, user=user, **kwargs):
        super().__init__(**kwargs)
        self.user = user

    def get(self, path: str, data: dict = None, **extra):
        request = super().get(path, data, **extra)
        request.user = self.user
        return request
