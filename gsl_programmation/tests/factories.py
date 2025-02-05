from datetime import date

from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from gsl_core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe


class DsilEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe

    type = Enveloppe.TYPE_DSIL
    montant = Faker("random_number", digits=5)
    annee = date.today().year
    perimetre = SubFactory(PerimetreRegionalFactory)


class DetrEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe

    type = Enveloppe.TYPE_DETR
    montant = Faker("random_number", digits=5)
    annee = date.today().year
    perimetre = SubFactory(PerimetreDepartementalFactory)
