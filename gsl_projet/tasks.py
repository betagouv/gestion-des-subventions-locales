from celery import shared_task

from gsl_demarches_simplifiees.models import Dossier

from .models import Projet


@shared_task
def update_projet_from_dossier(ds_dossier_number):
    ds_dossier = Dossier.objects.get(ds_number=ds_dossier_number)
    Projet.get_or_create_from_ds_dossier(ds_dossier)


@shared_task
def create_all_projets_from_dossiers():
    dossiers = Dossier.objects.exclude(ds_state="")
    for dossier in dossiers.all():
        update_projet_from_dossier.delay(dossier.ds_number)
