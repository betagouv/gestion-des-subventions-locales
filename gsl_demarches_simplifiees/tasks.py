from celery import shared_task

from gsl_demarches_simplifiees.importer.demarche import (
    refresh_field_mappings_on_demarche,
    save_demarche_from_ds,
)
from gsl_demarches_simplifiees.importer.dossier import (
    refresh_dossier_from_saved_data,
    save_demarche_dossiers_from_ds,
)


@shared_task
def task_save_demarche_from_ds(demarche_number):
    return save_demarche_from_ds(demarche_number)


@shared_task
def task_refresh_field_mappings_on_demarche(demarche_number):
    return refresh_field_mappings_on_demarche(demarche_number)


@shared_task
def task_save_demarche_dossiers_from_ds(demarche_number):
    return save_demarche_dossiers_from_ds(demarche_number)


@shared_task
def task_refresh_dossier_from_saved_data(dossier_number):
    refresh_dossier_from_saved_data(dossier_number)
