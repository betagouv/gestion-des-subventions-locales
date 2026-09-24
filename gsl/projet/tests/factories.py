from decimal import Decimal
from random import randint

import factory
from django.utils import timezone

from gsl_core.tests.factories import (
    AdresseFactory,
    CollegueFactory,
    DepartementFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

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


def _default_enveloppe(obj):
    """The enveloppe a treated dotation must carry. On the projet's own
    perimetre, the one spelling that always satisfies `contains_or_equal`
    whatever level that perimetre sits at."""
    if obj.status == ProjetStatus.PROCESSING:
        return None
    perimetre = obj.projet.dossier_ds.perimetre
    if obj.dotation == DOTATION_DETR:
        enveloppe = DetrEnveloppeFactory(perimetre=perimetre)
    else:
        enveloppe = DsilEnveloppeFactory(perimetre=perimetre)
    return enveloppe.delegation_root


def _default_montant(obj):
    if obj.status == ProjetStatus.PROCESSING:
        return None
    if obj.status != ProjetStatus.ACCEPTED:
        return Decimal(0)
    ceiling = obj.assiette or obj.projet.dossier_ds.finance_cout_total
    return Decimal(randint(0, int(ceiling))) if ceiling else Decimal(randint(1, 99_999))


class EnveloppeProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EnveloppeProjet
        django_get_or_create = ("projet", "dotation")

    projet = factory.SubFactory(ProjetFactory)
    dotation = factory.fuzzy.FuzzyChoice(DOTATIONS)
    status = factory.fuzzy.FuzzyChoice(ProjetStatus.values)
    detr_avis_commission = factory.Faker("boolean")
    assiette = None

    # The three below travel together: a treated dotation is a programmed one,
    # a dotation still being processed carries none of them.
    enveloppe = factory.LazyAttribute(_default_enveloppe)
    montant = factory.LazyAttribute(_default_montant)
    date_programmation = factory.LazyAttribute(
        lambda o: None if o.status == ProjetStatus.PROCESSING else timezone.now()
    )


class DetrProjetFactory(EnveloppeProjetFactory):
    dotation = DOTATION_DETR


class DsilProjetFactory(EnveloppeProjetFactory):
    dotation = DOTATION_DSIL


class ProjetNoteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjetNote

    projet = factory.SubFactory(ProjetFactory)
    title = factory.Faker("sentence", locale="fr_FR")
    content = factory.Faker("text", locale="fr_FR")
    created_by = factory.SubFactory(CollegueFactory)
