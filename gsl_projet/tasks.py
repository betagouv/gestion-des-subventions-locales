from celery import shared_task

from gsl_demarches_simplifiees.models import Dossier

from .models import Projet


@shared_task
def update_projet_from_dossier(ds_dossier_number):
    ds_dossier = Dossier.objects.get(ds_number=ds_dossier_number)
    Projet.get_or_create_from_ds_dossier(ds_dossier)
