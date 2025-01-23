from datetime import date

from factory import Faker, LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from gsl_core.tests.factories import (
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe, Simulation, SimulationProjet
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


class SimulationFactory(DjangoModelFactory):
    class Meta:
        model = Simulation

    slug = Sequence(lambda n: f"simulation-{n}")
    enveloppe = SubFactory(DetrEnveloppeFactory)


class SimulationProjetFactory(DjangoModelFactory):
    class Meta:
        model = SimulationProjet

    simulation = SubFactory(SimulationFactory)
    enveloppe = LazyAttribute(lambda o: o.simulation.enveloppe)
    projet = SubFactory(ProjetFactory)
    montant = Faker("random_number", digits=5)
    taux = Faker("random_number", digits=2)
    status = SimulationProjet.STATUS_DRAFT
