from random import randint
from typing import cast

from factory import LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from gsl.projet.constants import DOTATION_DETR, PROJET_STATUS_PROCESSING
from gsl.projet.tests.factories import DetrEnveloppeFactory, EnveloppeProjetFactory

from ..models import Simulation, SimulationProjet


class SimulationFactory(DjangoModelFactory):
    class Meta:
        model = Simulation

    slug = Sequence(lambda n: f"simulation-{n}")
    title = Sequence(lambda n: f"Simulation {n}")
    enveloppe = SubFactory(DetrEnveloppeFactory)


class SimulationProjetFactory(DjangoModelFactory):
    class Meta:
        model = SimulationProjet

    enveloppe_projet = SubFactory(EnveloppeProjetFactory)
    simulation = LazyAttribute(
        lambda obj: SimulationFactory(
            enveloppe__dotation=obj.enveloppe_projet.dotation,
            enveloppe__perimetre=obj.enveloppe_projet.projet.dossier_ds.perimetre,
        )
    )
    montant = LazyAttribute(
        lambda obj: randint(
            0,
            obj.enveloppe_projet.assiette
            or obj.enveloppe_projet.projet.dossier_ds.finance_cout_total
            or 1000,
        )
    )
    status = SimulationProjet.STATUS_PROCESSING


def make_detr_simu_projet(
    perimetre,
    simulation,
    *,
    dotation_status=PROJET_STATUS_PROCESSING,
    simu_status=SimulationProjet.STATUS_PROCESSING,
    assiette=10_000,
    montant=1000,
    **kwargs,
) -> SimulationProjet:
    """
    Build a DETR SimulationProjet anchored to `perimetre` and `simulation`.
    Consolidates the per-test `_make_simu_projet` helpers used across the bulk
    status tests so they share a single signature.
    """
    enveloppe_projet = EnveloppeProjetFactory(
        status=dotation_status,
        projet__dossier_ds__perimetre=perimetre,
        dotation=DOTATION_DETR,
        assiette=assiette,
    )
    return cast(
        SimulationProjet,
        SimulationProjetFactory(
            enveloppe_projet=enveloppe_projet,
            status=simu_status,
            montant=montant,
            simulation=simulation,
            **kwargs,
        ),
    )
