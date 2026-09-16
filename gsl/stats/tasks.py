from celery import shared_task

from gsl.celery import TASK_PRIORITY_LOW

from .importers.dgcl import import_dgcl_subventions
from .importers.fonds_vert import import_fonds_vert_subventions


@shared_task(priority=TASK_PRIORITY_LOW)
def fetch_subventions_dgcl():
    return import_dgcl_subventions()


@shared_task(priority=TASK_PRIORITY_LOW)
def fetch_subventions_fonds_vert():
    return import_fonds_vert_subventions()
