import logging

from celery import shared_task
from django.core.files.storage import default_storage

from .importer import import_chorus_file

logger = logging.getLogger(__name__)


@shared_task
def import_chorus_file_task(key):
    try:
        with default_storage.open(key) as file:
            result = import_chorus_file(file)
    finally:
        default_storage.delete(key)
    logger.info(
        "Import Chorus %s : %s nouvelle(s) ligne(s), %s rattachée(s) à un dossier, "
        "%s déjà présente(s), %s ignorée(s).",
        key,
        result.imported,
        result.matched,
        result.duplicate,
        result.skipped,
    )
