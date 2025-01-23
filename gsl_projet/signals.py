from django.db.models.signals import post_save
from django.dispatch import receiver

from gsl_demarches_simplifiees.models import Dossier

from .tasks import update_projet_from_dossier


@receiver(post_save, sender=Dossier, dispatch_uid="create_projet")
def create_projet_from_valid_dossier(sender, instance: Dossier, *args, **kwargs):
    if not instance.ds_state:
        return
    update_projet_from_dossier.delay(instance.ds_number)
