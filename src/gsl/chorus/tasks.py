from dataclasses import asdict

from celery import shared_task
from django.core.files.storage import default_storage

from .importer import import_chorus_file


@shared_task
def import_chorus_file_task(key):
    try:
        with default_storage.open(key) as file:
            result = import_chorus_file(file)
    finally:
        default_storage.delete(key)
    # Stored as the TaskResult's result, readable from the admin.
    return asdict(result)
