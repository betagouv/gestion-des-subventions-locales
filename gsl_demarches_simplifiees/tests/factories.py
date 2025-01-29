from datetime import timezone

import factory
import factory.fuzzy
from django.db.models.signals import post_save

from gsl_core.tests.factories import AdresseFactory

from ..models import Demarche, Dossier, NaturePorteurProjet, PersonneMorale


class DemarcheFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Demarche

    ds_id = factory.Sequence(lambda n: f"demarche-{n}")
    ds_number = factory.Faker("random_int", min=1000000, max=9999999)
    ds_title = "Titre de la démarche"
    ds_state = Demarche.STATE_PUBLIEE


class PersonneMoraleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PersonneMorale

    siret = factory.Sequence(lambda n: f"personnemorale-{n}")
    raison_sociale = factory.Faker("word", locale="fr_FR")
    address = factory.SubFactory(AdresseFactory)


class NaturePorteurProjetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NaturePorteurProjet

    label = factory.Sequence(lambda n: f"nature-porteur-projet-{n}")


@factory.django.mute_signals(post_save)
class DossierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dossier

    ds_demarche = factory.SubFactory(DemarcheFactory)
    ds_id = factory.Sequence(lambda n: f"dossier-{n}")
    ds_number = factory.Faker("random_int", min=1000000, max=9999999)
    ds_state = Dossier.STATE_EN_INSTRUCTION
    ds_demandeur = factory.SubFactory(PersonneMoraleFactory)
    ds_date_depot = factory.Faker(
        "date_time_this_year", before_now=True, tzinfo=timezone.utc
    )
    ds_date_traitement = factory.Faker(
        "date_time_this_year", before_now=True, tzinfo=timezone.utc
    )
    porteur_de_projet_nature = factory.SubFactory(NaturePorteurProjetFactory)
    demande_dispositif_sollicite = factory.fuzzy.FuzzyChoice(
        [
            Dossier.DEMANDE_DISPOSITIF_SOLLICITE_VALUES[0][0],
            Dossier.DEMANDE_DISPOSITIF_SOLLICITE_VALUES[1][0],
        ]
    )
