from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from gsl_notification.models import (
    Annexe,
    ArreteEtLettreSignes,
    ModeleArrete,
    ModeleLettreNotification,
)


@receiver(post_delete, sender=Annexe)
@receiver(post_delete, sender=ArreteEtLettreSignes)
def delete_file_after_instance_deletion(
    sender, instance: ArreteEtLettreSignes | Annexe, *args, **kwargs
):
    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except FileNotFoundError:  # ou l'exception S3 adéquate
        pass


@receiver(post_save, sender=ArreteEtLettreSignes)
@receiver(post_save, sender=Annexe)
def trigger_antivirus_scan(sender, instance, created, **kwargs):
    if created and not settings.BYPASS_ANTIVIRUS:
        from gsl_notification.tasks import scan_uploaded_document

        scan_uploaded_document.delay(sender._meta.label, instance.pk)


@receiver(post_save, sender=ModeleArrete)
@receiver(post_save, sender=ModeleLettreNotification)
def trigger_logo_antivirus_scan(sender, instance, created, update_fields, **kwargs):
    if settings.BYPASS_ANTIVIRUS:
        return

    # We scan even if the logo field is saved, even if it hasn't changed (it's easier)
    if created or update_fields is None or "logo" in update_fields:
        from gsl_notification.tasks import scan_uploaded_document

        scan_uploaded_document.delay(sender._meta.label, instance.pk, "logo")


@receiver(post_delete, sender=ModeleLettreNotification)
@receiver(post_delete, sender=ModeleArrete)
def delete_logo_file_after_instance_deletion(
    sender, instance: ModeleArrete | ModeleLettreNotification, *args, **kwargs
):
    if not instance.logo:
        return
    try:
        instance.logo.delete(save=False)
    except FileNotFoundError:  # ou l'exception S3 adéquate
        pass
