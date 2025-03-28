import factory

from gsl_core.tests.factories import (
    AdresseFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..models import Demandeur, Dotation, Projet


class DotationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dotation
        django_get_or_create = ("label",)

    label = (factory.fuzzy.FuzzyChoice((Dotation.DETR, Dotation.DSIL)),)


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
    status = factory.fuzzy.FuzzyChoice(choice[0] for choice in Projet.STATUS_CHOICES)
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
