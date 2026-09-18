from datetime import date

import factory
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory

from gsl.projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl.projet.tests.factories import DotationProjetFactory
from gsl_core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe, ProgrammationProjet


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

    status = ProgrammationProjet.STATUS_ACCEPTED
    # The two models carry the same status in production; keep fixtures coherent
    # so a document's validation sees the status the test asked for.
    dotation_projet = SubFactory(
        DotationProjetFactory, status=factory.SelfAttribute("..status")
    )
    enveloppe = factory.LazyAttribute(
        lambda obj: DetrEnveloppeFactory(
            perimetre=PerimetreDepartementalFactory(
                departement=obj.dotation_projet.projet.dossier_ds.perimetre.departement,
                region=obj.dotation_projet.projet.dossier_ds.perimetre.region,
            )
        )
    )

    montant = Faker("random_number", digits=5)

    @factory.post_generation
    def save_projet(obj, create, extracted, **kwargs):
        obj.dotation_projet.projet.save()
