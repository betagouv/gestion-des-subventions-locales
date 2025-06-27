import datetime

import factory

from ..models import Arrete, ArreteSigne


class ArreteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Arrete

    programmation_projet = factory.SubFactory(
        "gsl_programmation.tests.factories.ProgrammationProjetFactory"
    )
    created_by = factory.SubFactory("gsl_core.tests.factories.CollegueFactory")
    created_at = datetime.datetime.now(datetime.UTC)
    updated_at = datetime.datetime.now(datetime.UTC)
    content = factory.LazyAttribute(lambda _: {"key": "value"})


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
