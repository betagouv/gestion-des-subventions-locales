from datetime import date

from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from gsl.core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_programmation.models import Enveloppe


class DsilEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe
        django_get_or_create = ("perimetre", "dotation", "annee")

    dotation = DOTATION_DSIL
    montant = Faker("random_number", digits=5)
    annee = date.today().year
    perimetre = SubFactory(PerimetreRegionalFactory)


class DetrEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe
        django_get_or_create = ("perimetre", "dotation", "annee")

    dotation = DOTATION_DETR
    montant = Faker("random_number", digits=5)
    annee = date.today().year
    perimetre = SubFactory(PerimetreDepartementalFactory)
