from random import randint

from factory import Faker, LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
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
    # TODO to remove
    projet = SubFactory(ProjetFactory)
    dotation_projet = LazyAttribute(
        lambda obj: DotationProjetFactory(
            projet=obj.projet, dotation=obj.simulation.enveloppe.dotation
        )
    )
    montant = LazyAttribute(
        lambda obj: randint(
            0, obj.projet.assiette or obj.projet.dossier_ds.finance_cout_total or 1000
        )
    )
    taux = Faker("random_number", digits=2)
    status = SimulationProjet.STATUS_PROCESSING
