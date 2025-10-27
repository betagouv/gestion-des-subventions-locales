from itertools import batched

from celery import shared_task

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.models import Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService

from .services.projet_services import ProjetService


## Projets and Co
### for all
@shared_task
def task_create_or_update_projets_and_co_from_all_dossiers(
    batch_size=500,
):
    dossiers = Dossier.objects.exclude(ds_state="").values_list("ds_number", flat=True)

    for batch in batched(dossiers, batch_size):
        task_create_or_update_projets_and_co_batch.delay(batch)


### for a list
@shared_task
def task_create_or_update_projets_and_co_batch(dossier_numbers: tuple[int]):
    for ds_number in dossier_numbers:
        task_create_or_update_projet_and_co_from_dossier.delay(ds_number)


### for one
@shared_task
def task_create_or_update_projet_and_co_from_dossier(
    ds_dossier_number,
):
    ProjetService.create_or_update_projet_and_co_from_dossier(ds_dossier_number)


## Dotation Projet
### for all
@shared_task
def task_create_or_update_dotation_projets_from_all_projets(batch_size=500):
    projets = Projet.objects.all().values_list("pk", flat=True)
    for batch in batched(projets, batch_size):
        task_create_or_update_dotation_projets_from_projet_batch.delay(batch)


### for a list
@shared_task
def task_create_or_update_dotation_projets_from_projet_batch(
    dossier_numbers: tuple[int],
):
    for ds_number in dossier_numbers:
        task_create_or_update_dotation_projet_from_projet.delay(ds_number)


### for one
@shared_task
def task_create_or_update_dotation_projet_from_projet(projet_id):
    projet = Projet.objects.get(id=projet_id)
    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)
