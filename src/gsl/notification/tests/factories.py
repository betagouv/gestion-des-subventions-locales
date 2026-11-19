import datetime

import factory

from dn.sync.models import Dotation

from ..models import GeneratedDocument, ModeleDocument, UploadedDocument


class ModeleArreteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ModeleDocument

    type = GeneratedDocument.Type.ARRETE
    name = factory.Sequence(lambda n: f"Modele {n}")
    description = "La description du modèle"
    perimetre = factory.SubFactory("gsl.core.tests.factories.PerimetreFactory")
    dotation = factory.Iterator([Dotation.DETR, Dotation.DSIL])
    logo = factory.django.ImageField(filename="logo.png")
    logo_alt_text = factory.Faker("word")
    top_right_text = "Le texte en haut à droite du modèle"
    content = "<p>Contenu du modèle</p>"
    created_at = factory.Faker("date_time")
    created_by = factory.SubFactory("gsl.core.tests.factories.CollegueFactory")
    updated_at = factory.Faker("date_time")


class ModeleLettreNotificationFactory(ModeleArreteFactory):
    type = GeneratedDocument.Type.LETTRE


class ModeleLettreRefusFactory(ModeleArreteFactory):
    type = GeneratedDocument.Type.LETTRE_REFUS


class ArreteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GeneratedDocument

    type = GeneratedDocument.Type.ARRETE
    enveloppe_projet = factory.SubFactory(
        "gsl.projet.tests.factories.EnveloppeProjetFactory", status="accepted"
    )
    modele = factory.LazyAttribute(
        lambda obj: ModeleArreteFactory(
            dotation=obj.enveloppe_projet.dotation,
        )
    )
    created_by = factory.SubFactory("gsl.core.tests.factories.CollegueFactory")
    created_at = datetime.datetime.now(datetime.UTC)
    updated_at = datetime.datetime.now(datetime.UTC)
    content = "<p>Contenu du doc</p>"
    size = 100000  # 100 KB


class LettreNotificationFactory(ArreteFactory):
    type = GeneratedDocument.Type.LETTRE
    modele = factory.LazyAttribute(
        lambda obj: ModeleLettreNotificationFactory(
            dotation=obj.enveloppe_projet.dotation,
        )
    )


class LettreRefusFactory(ArreteFactory):
    type = GeneratedDocument.Type.LETTRE_REFUS
    enveloppe_projet = factory.SubFactory(
        "gsl.projet.tests.factories.EnveloppeProjetFactory", status="refused"
    )
    modele = factory.LazyAttribute(
        lambda obj: ModeleLettreRefusFactory(
            dotation=obj.enveloppe_projet.dotation,
        )
    )


class LettreEtArreteSignesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UploadedDocument

    type = UploadedDocument.Type.LETTRE_ET_ARRETE_SIGNES
    file = factory.django.FileField(
        filename="test_file.pdf",
        content_type="application/pdf",
        size=1024,  # 1 KB
    )
    enveloppe_projet = factory.SubFactory(
        "gsl.projet.tests.factories.EnveloppeProjetFactory", status="accepted"
    )
    created_by = factory.SubFactory("gsl.core.tests.factories.CollegueFactory")
    created_at = datetime.datetime.now(datetime.UTC)


class AnnexeFactory(LettreEtArreteSignesFactory):
    type = UploadedDocument.Type.ANNEXE


class LettreRefusSigneeFactory(LettreEtArreteSignesFactory):
    type = UploadedDocument.Type.LETTRE_REFUS_SIGNEE
    enveloppe_projet = factory.SubFactory(
        "gsl.projet.tests.factories.EnveloppeProjetFactory",
        status="refused",
    )
