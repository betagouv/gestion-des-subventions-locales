import factory

from gsl_core.tests.factories import (
    AdresseFactory,
    CollegueFactory,
    DepartementFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
    PROJET_STATUS_CHOICES,
)

from ..models import CategorieDetr, Demandeur, DotationProjet, Projet, ProjetNote


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


class CategorieDetrFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CategorieDetr
        django_get_or_create = ("departement", "annee", "rang")

    departement = factory.SubFactory(DepartementFactory)
    annee = factory.Faker("random_int", min=2024, max=2027)
    rang = factory.Sequence(lambda n: n)
    libelle = factory.Faker("sentence", locale="fr_FR")
    is_current = True


class ProjetNoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjetNote

    projet = factory.SubFactory(ProjetFactory)
    title = factory.Faker("sentence", locale="fr_FR")
    content = factory.Faker("text", locale="fr_FR")
    created_by = factory.SubFactory(CollegueFactory)
