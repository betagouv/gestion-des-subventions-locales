from celery import shared_task

from gsl_demarches_simplifiees.importer.demarche import (
    refresh_field_mappings_on_demarche,
    save_demarche_from_ds,
)
from gsl_demarches_simplifiees.importer.dossier import (
    refresh_dossier_from_saved_data,
    save_demarche_dossiers_from_ds,
    save_one_dossier_from_ds,
)
from gsl_demarches_simplifiees.models import Demarche, Dossier


## Refresh demarches from DN
#### of every demarches => useful in cron tasks !
@shared_task
def task_refresh_every_demarche(refresh_only_if_demarche_has_been_updated=True):
    for d in Demarche.objects.all():
        task_save_demarche_from_ds.delay(
            d.ds_number, refresh_only_if_demarche_has_been_updated
        )


#### of one demarche
@shared_task
def task_save_demarche_from_ds(
    demarche_number, refresh_only_if_demarche_has_been_updated=False
):
    return save_demarche_from_ds(
        demarche_number, refresh_only_if_demarche_has_been_updated
    )


## Refresh dossiers
### from DN
#### of every published demarches
@shared_task
def task_fetch_ds_dossiers_for_every_published_demarche():
    for d in Demarche.objects.filter(ds_state=Demarche.STATE_PUBLIEE):
        task_save_demarche_dossiers_from_ds.delay(d.ds_number)


#### of one demarche
@shared_task
def task_save_demarche_dossiers_from_ds(
    demarche_number, using_updated_since: bool = True
):
    return save_demarche_dossiers_from_ds(demarche_number, using_updated_since)


#### of one dossier
@shared_task
def task_save_one_dossier_from_ds(
    dossier_number, refresh_only_if_dossier_has_been_updated=False
):
    dossier = Dossier.objects.get(ds_number=dossier_number)
    return save_one_dossier_from_ds(
        dossier,
        refresh_only_if_dossier_has_been_updated=refresh_only_if_dossier_has_been_updated,
    )


### from saved data
#### of one dossier
@shared_task
def task_refresh_dossier_from_saved_data(dossier_number):
    dossier = Dossier.objects.get(ds_number=dossier_number)
    refresh_dossier_from_saved_data(dossier)


## Refresh demarche field mappings
## from saved data if existing else from DN
@shared_task
def task_refresh_field_mappings_from_demarche_data(demarche_number):
    return refresh_field_mappings_on_demarche(demarche_number)
