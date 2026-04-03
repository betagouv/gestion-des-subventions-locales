import factory

from gsl_ds_proxy.models import ProxyToken


class ProxyTokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProxyToken

    label = factory.Sequence(lambda n: f"Token {n}")
    is_active = True
