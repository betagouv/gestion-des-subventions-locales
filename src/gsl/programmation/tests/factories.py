from datetime import date

from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from dn.sync.models import Dotation
from gsl.core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.programmation.models import Enveloppe


class DsilEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe
        django_get_or_create = ("perimetre", "dotation", "annee")

    dotation = Dotation.DSIL
    montant = Faker("random_number", digits=5)
    annee = date.today().year
    perimetre = SubFactory(PerimetreRegionalFactory)


class DetrEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe
        django_get_or_create = ("perimetre", "dotation", "annee")

    dotation = Dotation.DETR
    montant = Faker("random_number", digits=5)
    annee = date.today().year
    perimetre = SubFactory(PerimetreDepartementalFactory)
