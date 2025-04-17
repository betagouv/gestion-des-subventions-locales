from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet

from .tasks import update_projet_from_dossier


@receiver(post_save, sender=Dossier, dispatch_uid="create_projet")
def create_projet_from_valid_dossier(sender, instance: Dossier, *args, **kwargs):
    if not instance.ds_state:
        return
    update_projet_from_dossier.delay(instance.ds_number)


@receiver(
    [post_save, post_delete], sender=DotationProjet, dispatch_uid="update_projet_status"
)
def update_projet_status(sender, instance: DotationProjet, **kwargs):
    """N’a pas été géré par un GeneratedField car est dépendant de champs d’autres modèles"""
    instance.projet.status = get_projet_status(instance)
    instance.projet.save()


def get_projet_status(dotation_projet: DotationProjet):
    projet_dotation_projets = DotationProjet.objects.filter(
        projet=dotation_projet.projet
    )
    if not projet_dotation_projets:
        return None
    if any(dp.status == PROJET_STATUS_ACCEPTED for dp in projet_dotation_projets):
        return PROJET_STATUS_ACCEPTED
    if any(dp.status == PROJET_STATUS_PROCESSING for dp in projet_dotation_projets):
        return PROJET_STATUS_PROCESSING
    if any(dp.status == PROJET_STATUS_REFUSED for dp in projet_dotation_projets):
        return PROJET_STATUS_REFUSED
    return PROJET_STATUS_DISMISSED
