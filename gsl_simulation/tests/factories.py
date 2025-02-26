from factory import Faker, Sequence, SubFactory
from factory.django import DjangoModelFactory

from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import Simulation, SimulationProjet


class SimulationFactory(DjangoModelFactory):
    class Meta:
        model = Simulation

    slug = Sequence(lambda n: f"simulation-{n}")
    enveloppe = SubFactory(DetrEnveloppeFactory)


class SimulationProjetFactory(DjangoModelFactory):
    class Meta:
        model = SimulationProjet

    simulation = SubFactory(SimulationFactory)
    projet = SubFactory(ProjetFactory)
    montant = Faker("random_number", digits=5)
    taux = Faker("random_number", digits=2)
    status = SimulationProjet.STATUS_PROCESSING
