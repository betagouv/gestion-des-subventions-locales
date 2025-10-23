from datetime import timezone

import factory
import factory.fuzzy
from django.db.models.signals import post_save

from gsl_core.tests.factories import AdresseFactory
from gsl_core.tests.factories import ArrondissementFactory as CoreArrondissementFactory
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL

from ..models import (
    Arrondissement as DsArrondissement,
)
from ..models import (
    CritereEligibiliteDetr,
    Demarche,
    Dossier,
    DsChoiceLibelle,
    FieldMappingForComputer,
    NaturePorteurProjet,
    PersonneMorale,
    Profile,
)


class DemarcheFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Demarche

    ds_id = factory.Sequence(lambda n: f"demarche-{n}")
    ds_number = factory.Sequence(lambda n: 1_000_000 + n)
    ds_title = "Titre de la démarche"
    ds_state = Demarche.STATE_PUBLIEE


class PersonneMoraleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PersonneMorale

    siret = factory.Sequence(lambda n: f"personnemorale-{n}")
    raison_sociale = factory.Faker("word", locale="fr_FR")
    address = factory.SubFactory(AdresseFactory)


class DsLibelleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DsChoiceLibelle

    label = factory.Sequence(lambda n: f"dslibelle-{n}")


class DsArrondissementFactory(DsLibelleFactory):
    class Meta:
        model = DsArrondissement

    core_arrondissement = factory.SubFactory(CoreArrondissementFactory)


class CritereEligibiliteDetrFactory(DsLibelleFactory):
    class Meta:
        model = CritereEligibiliteDetr


class NaturePorteurProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NaturePorteurProjet

    label = factory.Sequence(lambda n: f"nature-porteur-projet-{n}")


class ProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Profile

    ds_id = factory.Sequence(lambda n: f"user-{n}")
    ds_email = factory.Faker("email")


@factory.django.mute_signals(post_save)
class DossierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dossier

    ds_demarche = factory.SubFactory(DemarcheFactory)
    ds_id = factory.Sequence(lambda n: f"dossier-{n}")
    ds_number = factory.Faker("random_int", min=1000000, max=9999999)
    ds_state = Dossier.STATE_EN_INSTRUCTION
    ds_demandeur = factory.SubFactory(PersonneMoraleFactory)
    porteur_de_projet_arrondissement = factory.SubFactory(DsArrondissementFactory)
    ds_date_depot = factory.Faker(
        "date_time_this_year", before_now=True, tzinfo=timezone.utc
    )
    ds_date_traitement = factory.Faker(
        "date_time_this_year", before_now=True, tzinfo=timezone.utc
    )
    porteur_de_projet_nature = factory.SubFactory(NaturePorteurProjetFactory)
    demande_dispositif_sollicite = factory.fuzzy.FuzzyChoice(
        [
            DOTATION_DETR,
            DOTATION_DSIL,
        ]
    )


CHOICES = [field.name for field in Dossier.MAPPED_FIELDS]


class FieldMappingForComputerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FieldMappingForComputer

    demarche = factory.SubFactory(DemarcheFactory)
    django_field = factory.fuzzy.FuzzyChoice(CHOICES)
