from decimal import Decimal
from random import randint

import factory
from django.utils import timezone

from gsl.core.tests.factories import (
    AdresseFactory,
    CollegueFactory,
    DepartementFactory,
)
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory

from ..constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
    ProjetStatus,
)
from ..models import EnveloppeProjet, Projet, ProjetNote


class ProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Projet

    dossier_ds = factory.SubFactory(DossierFactory)
    address = factory.SubFactory(AdresseFactory)
    departement = factory.SubFactory(DepartementFactory)


class SubmittedProjetFactory(ProjetFactory):
    dossier_ds = factory.SubFactory(
        DossierFactory,
        ds_state=factory.fuzzy.FuzzyChoice(
            (Dossier.State.EN_CONSTRUCTION, Dossier.State.EN_INSTRUCTION)
        ),
    )


class ProcessedProjetFactory(ProjetFactory):
    dossier_ds = factory.SubFactory(
        DossierFactory,
        ds_state=factory.fuzzy.FuzzyChoice(
            (Dossier.State.ACCEPTE, Dossier.State.REFUSE, Dossier.State.SANS_SUITE)
        ),
    )


def _default_enveloppe(obj):
    """On the projet's own perimetre, the one spelling that always satisfies
    `contains_or_equal` whatever level that perimetre sits at."""
    perimetre = obj.projet.dossier_ds.perimetre
    if obj.dotation == DOTATION_DETR:
        enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
    else:
        enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    return enveloppe.delegation_root


def _default_montant(obj):
    if obj.status != ProjetStatus.ACCEPTED:
        return None
    ceiling = obj.assiette or obj.projet.dossier_ds.finance_cout_total
    return Decimal(randint(0, int(ceiling))) if ceiling else Decimal(randint(1, 99_999))


class EnveloppeProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EnveloppeProjet
        django_get_or_create = ("projet", "enveloppe")

    class Params:
        dotation = factory.fuzzy.FuzzyChoice(DOTATIONS)

    projet = factory.SubFactory(ProjetFactory)
    status = factory.fuzzy.FuzzyChoice(ProjetStatus.values)
    detr_avis_commission = factory.Faker("boolean")
    assiette = None

    enveloppe = factory.LazyAttribute(_default_enveloppe)

    # A CheckConstraint ties both to the status, so overriding one alone fails.
    montant = factory.LazyAttribute(_default_montant)
    date_programmation = factory.LazyAttribute(
        lambda o: None if o.status == ProjetStatus.PROCESSING else timezone.now()
    )


class DetrProjetFactory(EnveloppeProjetFactory):
    class Params:
        dotation = DOTATION_DETR


class DsilProjetFactory(EnveloppeProjetFactory):
    class Params:
        dotation = DOTATION_DSIL


class ProjetNoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjetNote

    projet = factory.SubFactory(ProjetFactory)
    title = factory.Faker("sentence", locale="fr_FR")
    content = factory.Faker("text", locale="fr_FR")
    created_by = factory.SubFactory(CollegueFactory)
