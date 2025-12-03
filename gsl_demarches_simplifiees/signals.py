import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from gsl_core.models import Arrondissement as CoreArrondissement
from gsl_demarches_simplifiees.models import Arrondissement as DsArrondissement
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tasks import task_refresh_dossier_from_saved_data

logger = logging.getLogger(__name__)


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
    logger.warning(
        f"Unable to match a CoreArrondissement with DS Arrondissement '{instance.label}'."
    )


@receiver(post_save, sender=DsArrondissement)
def refresh_associated_projets(sender, instance: DsArrondissement, *args, **kwargs):
    if instance.core_arrondissement is None:
        return

    for dossier_number in Dossier.objects.filter(
        porteur_de_projet_arrondissement=instance
    ).values_list("ds_number", flat=True):
        task_refresh_dossier_from_saved_data.delay(dossier_number)
