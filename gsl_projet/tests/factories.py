import factory

from gsl_core.tests.factories import (
    AdresseFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
    PROJET_STATUS_CHOICES,
)

from ..models import Demandeur, DotationProjet, Projet


class DemandeurFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Demandeur

    siret = factory.Sequence(lambda n: f"siret-{n}")
    name = factory.Faker("city", locale="fr_FR")

    address = factory.SubFactory(AdresseFactory)


class ProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Projet

    dossier_ds = factory.SubFactory(DossierFactory)
    address = factory.SubFactory(AdresseFactory)
    departement = factory.SubFactory(DepartementFactory)
    demandeur = factory.SubFactory(DemandeurFactory)
    perimetre = factory.LazyAttribute(
        lambda obj: PerimetreArrondissementFactory(
            arrondissement=obj.dossier_ds.ds_demandeur.address.commune.arrondissement
        )
    )


class SubmittedProjetFactory(ProjetFactory):
    dossier_ds = factory.SubFactory(
        DossierFactory,
        ds_state=factory.fuzzy.FuzzyChoice(
            (Dossier.STATE_EN_CONSTRUCTION, Dossier.STATE_EN_INSTRUCTION)
        ),
    )


class ProcessedProjetFactory(ProjetFactory):
    dossier_ds = factory.SubFactory(
        DossierFactory,
        ds_state=factory.fuzzy.FuzzyChoice(
            (Dossier.STATE_ACCEPTE, Dossier.STATE_REFUSE, Dossier.STATE_SANS_SUITE)
        ),
    )


class DotationProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DotationProjet
        django_get_or_create = ("projet", "dotation")

    projet = factory.SubFactory(ProjetFactory)
    dotation = factory.fuzzy.FuzzyChoice(DOTATIONS)
    status = factory.fuzzy.FuzzyChoice(choice[0] for choice in PROJET_STATUS_CHOICES)
    detr_avis_commission = factory.Faker("boolean")


class DetrProjetFactory(DotationProjetFactory):
    dotation = DOTATION_DETR


class DsilProjetFactory(DotationProjetFactory):
    dotation = DOTATION_DSIL
