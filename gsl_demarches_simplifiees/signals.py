from django.db.models.signals import pre_save
from django.dispatch import receiver

from gsl_core.models import Arrondissement as CoreArrondissement

from .models import Arrondissement as DsArrondissement


@receiver(pre_save, sender=DsArrondissement)
def associate_with_core_arrondissement(
    sender, instance: DsArrondissement, *args, **kwargs
):
    if instance.core_arrondissement is not None:
        return
    for core_arrondissement in CoreArrondissement.objects.select_related(
        "departement"
    ).all():
        # instance label is like "43 - Haute-Loire - arrondissement de Brioude"
        if instance.label.startswith(
            core_arrondissement.departement.insee_code
        ) and instance.label.endswith(core_arrondissement.name):
            instance.core_arrondissement = core_arrondissement
            return
