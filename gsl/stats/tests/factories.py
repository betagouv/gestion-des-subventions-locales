import factory

from ..models import Subvention


class SubventionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subvention

    source = Subvention.SOURCE_DGCL
    siren = factory.Sequence(lambda n: f"{n:09d}")
    exercice = 2024
    dispositif = "DETR"
    programme = 119
    intitule = factory.Faker("sentence", locale="fr_FR")
    cout_total = 1000
