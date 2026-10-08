import secrets

import factory

from dn.proxy.models import ProxyToken
from gsl_demarches_simplifiees.tests.factories import DemarcheFactory


class ProxyTokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProxyToken

    label = factory.Sequence(lambda n: f"Token {n}")
    demarche = factory.SubFactory(DemarcheFactory)
    groupe_instructeur_ds_id = factory.Sequence(lambda n: f"GROUPE-{n}")
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        plaintext = kwargs.pop("plaintext_key", None) or secrets.token_hex(32)
        kwargs["key_hash"] = model_class.hash_key(plaintext)
        instance = super()._create(model_class, *args, **kwargs)
        instance.plaintext_key = plaintext
        return instance
