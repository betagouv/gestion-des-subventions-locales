from datetime import date

from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from gsl_core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.tests.factories import ProjetFactory


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


class ProgrammationProjetFactory(DjangoModelFactory):
    class Meta:
        model = ProgrammationProjet

    projet = SubFactory(ProjetFactory)
    enveloppe = SubFactory(DetrEnveloppeFactory)
    montant = Faker("random_number", digits=5)
    taux = Faker("random_number", digits=2)
