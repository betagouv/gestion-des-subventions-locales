import factory

from gsl.projet.tests.factories import ProjetFactory

from ..models import ProjetAction


class ProjetActionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjetAction

    projet = factory.SubFactory(ProjetFactory)
