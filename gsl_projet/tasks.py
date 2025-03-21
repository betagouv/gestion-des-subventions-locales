from itertools import batched

from celery import shared_task

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.services.programmation_projet_service import (
    ProgrammationProjetService,
)
from gsl_simulation.services.simulation_projet_service import SimulationProjetService

from .services import ProjetService


@shared_task
def update_projet_from_dossier(ds_dossier_number):
    ds_dossier = Dossier.objects.get(ds_number=ds_dossier_number)
    ProjetService.create_or_update_from_ds_dossier(ds_dossier)


@shared_task
def create_all_projets_from_dossiers():
    dossiers = Dossier.objects.exclude(ds_state="")
    for dossier in dossiers.all():
        update_projet_from_dossier.delay(dossier.ds_number)


@shared_task
def create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier(
    ds_dossier_number,
):
    ds_dossier = Dossier.objects.get(ds_number=ds_dossier_number)
    projet = ProjetService.create_or_update_from_ds_dossier(ds_dossier)
    SimulationProjetService.update_simulation_projets_from_projet(projet)
    ProgrammationProjetService.create_or_update_from_projet(projet)


@shared_task
def create_or_update_projets_and_its_simulation_and_programmation_projets_from_all_dossiers(
    batch_size=500,
):
    dossiers = Dossier.objects.exclude(ds_state="").values_list("ds_number", flat=True)

    for batch in batched(dossiers, batch_size):
        create_or_update_projets_batch.delay(batch)


@shared_task
def create_or_update_projets_batch(dossier_numbers: tuple[int]):
    for ds_number in dossier_numbers:
        create_or_update_projet_and_its_simulation_and_programmation_projets_from_dossier.delay(
            ds_number
        )
