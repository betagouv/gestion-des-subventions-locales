import datetime

import factory

from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL

from ..models import Arrete, ArreteSigne, ModeleArrete, ModeleLettreNotification


class ModeleArreteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ModeleArrete

    name = factory.Sequence(lambda n: f"Modele {n}")
    description = "La description du modèle"
    perimetre = factory.SubFactory("gsl_core.tests.factories.PerimetreFactory")
    dotation = factory.Iterator([DOTATION_DETR, DOTATION_DSIL])
    logo = factory.django.ImageField(filename="logo.png")
    logo_alt_text = factory.Faker("word")
    top_right_text = "Le texte en haut à droite du modèle"
    content = "<p>Contenu du modèle</p>"
    created_at = factory.Faker("date_time")
    created_by = factory.SubFactory("gsl_core.tests.factories.CollegueFactory")
    updated_at = factory.Faker("date_time")


class ModeleLettreNotificationFactory(ModeleArreteFactory):
    class Meta:
        model = ModeleLettreNotification


class ArreteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Arrete

    programmation_projet = factory.SubFactory(
        "gsl_programmation.tests.factories.ProgrammationProjetFactory"
    )
    modele = factory.SubFactory(ModeleArreteFactory)
    created_by = factory.SubFactory("gsl_core.tests.factories.CollegueFactory")
    created_at = datetime.datetime.now(datetime.UTC)
    updated_at = datetime.datetime.now(datetime.UTC)
    content = "<p>Contenu de l'arrêté</p>"


class ArreteSigneFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ArreteSigne

    file = factory.django.FileField(
        filename="test_file.pdf",
        content_type="application/pdf",
        size=1024,  # 1 KB
    )
    programmation_projet = factory.SubFactory(
        "gsl_programmation.tests.factories.ProgrammationProjetFactory"
    )
    created_by = factory.SubFactory("gsl_core.tests.factories.CollegueFactory")
    created_at = datetime.datetime.now(datetime.UTC)
