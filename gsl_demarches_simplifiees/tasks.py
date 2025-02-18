from celery import shared_task

from gsl_demarches_simplifiees.importer.demarche import (
    refresh_field_mappings_on_demarche,
    save_demarche_from_ds,
)
from gsl_demarches_simplifiees.importer.dossier import (
    refresh_dossier_from_saved_data,
    save_demarche_dossiers_from_ds,
)
from gsl_demarches_simplifiees.models import Demarche


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


@shared_task
def task_refresh_every_demarche():
    for d in Demarche.objects.all():
        task_save_demarche_from_ds.delay(d.ds_number)


@shared_task
def task_fetch_ds_dossiers_for_every_published_demarche():
    for d in Demarche.objects.filter(ds_state=Demarche.STATE_PUBLIEE):
        task_save_demarche_dossiers_from_ds.delay(d.ds_number)
