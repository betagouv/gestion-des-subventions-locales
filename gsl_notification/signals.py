from django.db.models.signals import post_delete
from django.dispatch import receiver

from gsl_notification.models import (
    Annexe,
    ArreteSigne,
    ModeleArrete,
    ModeleLettreNotification,
)


@receiver(post_delete, sender=Annexe)
@receiver(post_delete, sender=ArreteSigne)
def delete_file_after_instance_deletion(sender, instance: ArreteSigne, *args, **kwargs):
    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except FileNotFoundError:  # ou l'exception S3 adéquate
        pass


@receiver(post_delete, sender=ModeleLettreNotification)
@receiver(post_delete, sender=ModeleArrete)
def delete_logo_file_after_instance_deletion(
    sender, instance: ModeleArrete, *args, **kwargs
):
    if not instance.logo:
        return
    try:
        instance.logo.delete(save=False)
    except FileNotFoundError:  # ou l'exception S3 adéquate
        pass
