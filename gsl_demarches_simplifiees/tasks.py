from celery import shared_task

from gsl_demarches_simplifiees.importer.demarche import save_demarche_from_ds
from gsl_demarches_simplifiees.importer.dossier import save_demarche_dossiers_from_ds


@shared_task
def ds_save_one_demarche(demarche_number):
    return save_demarche_from_ds(demarche_number)


@shared_task
def ds_save_dossiers_from_demarche(demarche_number):
    return save_demarche_dossiers_from_ds(demarche_number)
