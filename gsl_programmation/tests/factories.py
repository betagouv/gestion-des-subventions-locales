from factory import Faker, Sequence, SubFactory
from factory.django import DjangoModelFactory

from gsl_core.tests.factories import DepartementFactory, RegionFactory
from gsl_programmation.models import Enveloppe, Simulation


class DsilEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe

    type = Enveloppe.TYPE_DSIL
    montant = Faker("random_number", digits=5)
    annee = 2024
    perimetre_region = SubFactory(RegionFactory)


class DetrEnveloppeFactory(DjangoModelFactory):
    class Meta:
        model = Enveloppe

    type = Enveloppe.TYPE_DETR
    montant = Faker("random_number", digits=5)
    annee = 2024
    perimetre_departement = SubFactory(DepartementFactory)


class SimulationFactory(DjangoModelFactory):
    class Meta:
        model = Simulation

    slug = Sequence(lambda n: f"simulation-{n}")
    enveloppe = SubFactory(DetrEnveloppeFactory)
