from django.db.models.signals import post_save
from django.dispatch import receiver

from gsl_demarches_simplifiees.models import Dossier

from .tasks import update_projet_from_dossier


@receiver(post_save, sender=Dossier)
def create_or_update_projet_after_dossier_save(
    sender, instance: Dossier, *args, **kwargs
):
    update_projet_from_dossier.delay(instance.ds_number)
