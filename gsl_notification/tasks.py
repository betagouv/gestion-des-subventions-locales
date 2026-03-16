import logging
import os
import subprocess
import tempfile

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from gsl_notification.models import (
    Annexe,
    ArreteEtLettreSignes,
    ModeleArrete,
    ModeleLettreNotification,
)

logger = logging.getLogger(__name__)

UPLOADED_DOCUMENT_MODELS = (ArreteEtLettreSignes, Annexe)
LOGO_SCANNED_MODELS = (ModeleArrete, ModeleLettreNotification)


def _scan_file(file_field) -> dict:
    """Download a file from storage to a temp location and scan it with clamdscan.

    Returns dict with keys: is_infected (bool), output (str).
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            with file_field.open("rb") as src:
                for chunk in src.chunks():
                    tmp.write(chunk)

        result = subprocess.run(
            [
                "clamdscan",
                f"--config-file={settings.CLAMAV_CONFIG_FILE}",
                "--fdpass",
                tmp_path,
            ],
            capture_output=True,
            text=True,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    match result.returncode:
        case 0:
            return {"is_infected": False, "output": result.stdout}
        case 1:
            return {"is_infected": True, "output": result.stdout}
        case _:
            raise RuntimeError(
                f"clamdscan exited with code {result.returncode}: {result.stdout}"
            )


def _update_scan_result(instance, scan_result):
    instance.last_scan = timezone.now()
    instance.is_infected = scan_result["is_infected"]
    instance.save(update_fields=["last_scan", "is_infected"])

    if scan_result["is_infected"]:
        logger.error(
            "Fichier infecté détecté : %s id=%s — %s",
            instance._meta.label,
            instance.pk,
            scan_result["output"],
        )


@shared_task
def scan_uploaded_document(model_label: str, pk: int, file_field_name: str = "file"):
    """Scan a single uploaded document for viruses."""
    if settings.BYPASS_ANTIVIRUS:
        return

    from django.apps import apps

    model_class = apps.get_model(model_label)
    instance = model_class.objects.get(pk=pk)

    file_field = getattr(instance, file_field_name)
    scan_result = _scan_file(file_field)
    _update_scan_result(instance, scan_result)


@shared_task
def scan_all_uploaded_documents():
    """Periodic task: rescan all uploaded documents."""
    if settings.BYPASS_ANTIVIRUS:
        return

    scanned = 0
    infected = 0

    models_and_fields = [
        (model_class, "file") for model_class in UPLOADED_DOCUMENT_MODELS
    ] + [(Model, "logo") for Model in LOGO_SCANNED_MODELS]

    for Model, field_name in models_and_fields:
        for instance in Model.objects.all().iterator():
            try:
                file_field = getattr(instance, field_name)
                scan_result = _scan_file(file_field)
                _update_scan_result(instance, scan_result)
                scanned += 1
                if scan_result["is_infected"]:
                    infected += 1
            except (FileNotFoundError, RuntimeError):
                logger.exception(
                    "Erreur lors de l'analyse de %s id=%s",
                    Model._meta.label,
                    instance.pk,
                )

    logger.info(
        "Analyse antivirus périodique terminée : %d fichiers analysés, %d infectés",
        scanned,
        infected,
    )
