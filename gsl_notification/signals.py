from django.conf import settings
from django.db.models.signals import post_delete, post_save

from gsl_notification.models import (
    MODELES,
    UPLOADED_DOCUMENTS,
)


def delete_file_after_instance_deletion(sender, instance, *args, **kwargs):
    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except FileNotFoundError:  # ou l'exception S3 adéquate
        pass


def trigger_antivirus_scan(sender, instance, created, **kwargs):
    if created and not settings.BYPASS_ANTIVIRUS:
        from gsl_notification.tasks import scan_uploaded_document

        scan_uploaded_document.delay(sender._meta.label, instance.pk)


for _model in UPLOADED_DOCUMENTS.values():
    post_delete.connect(delete_file_after_instance_deletion, sender=_model)
    post_save.connect(trigger_antivirus_scan, sender=_model)


def trigger_logo_antivirus_scan(sender, instance, created, update_fields, **kwargs):
    if settings.BYPASS_ANTIVIRUS:
        return

    # We scan even if the logo field is saved, even if it hasn't changed (it's easier)
    if created or update_fields is None or "logo" in update_fields:
        from gsl_notification.tasks import scan_uploaded_document

        scan_uploaded_document.delay(sender._meta.label, instance.pk, "logo")


def delete_logo_file_after_instance_deletion(sender, instance, *args, **kwargs):
    if not instance.logo:
        return
    try:
        instance.logo.delete(save=False)
    except FileNotFoundError:  # ou l'exception S3 adéquate
        pass


for _modele in MODELES.values():
    post_save.connect(trigger_logo_antivirus_scan, sender=_modele)
    post_delete.connect(delete_logo_file_after_instance_deletion, sender=_modele)
