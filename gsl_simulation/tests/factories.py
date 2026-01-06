from random import randint

from factory import LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import Simulation, SimulationProjet


class SimulationFactory(DjangoModelFactory):
    class Meta:
        model = Simulation

    slug = Sequence(lambda n: f"simulation-{n}")
    title = Sequence(lambda n: f"Simulation {n}")
    enveloppe = SubFactory(DetrEnveloppeFactory)


class SimulationProjetFactory(DjangoModelFactory):
    class Meta:
        model = SimulationProjet

    dotation_projet = SubFactory(DotationProjetFactory)
    simulation = LazyAttribute(
        lambda obj: SimulationFactory(enveloppe__dotation=obj.dotation_projet.dotation)
    )
    montant = LazyAttribute(
        lambda obj: randint(
            0,
            obj.dotation_projet.assiette
            or obj.dotation_projet.projet.dossier_ds.finance_cout_total
            or 1000,
        )
    )
    status = SimulationProjet.STATUS_PROCESSING
