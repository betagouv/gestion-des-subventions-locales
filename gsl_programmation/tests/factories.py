from datetime import date

import factory
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from gsl_core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.tests.factories import DotationProjetFactory


class EnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe

    dotation = Faker("random_element", elements=(DOTATION_DETR, DOTATION_DSIL))
    montant = Faker("random_number", digits=5)
    annee = date.today().year
    perimetre = SubFactory(PerimetreRegionalFactory)


class DsilEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe

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


class ProgrammationProjetFactory(DjangoModelFactory):
    class Meta:
        model = ProgrammationProjet

    dotation_projet = SubFactory(DotationProjetFactory)
    enveloppe = factory.LazyAttribute(
        lambda obj: DetrEnveloppeFactory(
            perimetre=PerimetreDepartementalFactory(
                departement=obj.dotation_projet.projet.perimetre.departement,
                region=obj.dotation_projet.projet.perimetre.region,
            )
        )
    )

    montant = Faker("random_number", digits=5)

    @factory.post_generation
    def save_projet(obj, create, extracted, **kwargs):
        obj.dotation_projet.projet.save()
