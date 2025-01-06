from django.db.models.signals import post_save
from django.dispatch import receiver

from gsl_demarches_simplifiees.models import Dossier

from .tasks import update_projet_from_dossier


@receiver(post_save, sender=Dossier)
def create_projet_from_valid_dossier(sender, instance: Dossier, *args, **kwargs):
    if not instance.ds_state or instance.ds_state == Dossier.STATE_EN_CONSTRUCTION:
        return
    update_projet_from_dossier.delay(instance.ds_number)