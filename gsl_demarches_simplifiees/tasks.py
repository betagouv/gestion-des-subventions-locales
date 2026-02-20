from datetime import datetime

from celery import shared_task
from django.utils import timezone

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
#### only new or modified dossiers
@shared_task
def task_fetch_new_or_modified_ds_dossiers_for_every_published_demarche():
    for d in Demarche.objects.filter(ds_state=Demarche.STATE_PUBLIEE):
        task_save_demarche_dossiers_from_ds.delay(d.ds_number, using_updated_since=True)


#### all dossiers
@shared_task
def task_fetch_all_ds_dossiers_for_every_published_demarche():
    for d in Demarche.objects.filter(ds_state=Demarche.STATE_PUBLIEE):
        task_save_demarche_dossiers_from_ds.delay(
            d.ds_number, using_updated_since=False
        )


#### of one demarche
@shared_task
def task_save_demarche_dossiers_from_ds(
    demarche_number,
    using_updated_since: bool = True,
    updated_after_iso: str | None = None,
):
    """
    :param updated_after_iso: date/heure en ISO (optionnel) — ne rafraîchir que les
        dossiers déposés après cette date/heure.
    """
    updated_after = None
    if updated_after_iso:
        updated_after = datetime.fromisoformat(updated_after_iso.replace("Z", "+00:00"))
        if timezone.is_naive(updated_after):
            updated_after = timezone.make_aware(updated_after)
    return save_demarche_dossiers_from_ds(
        demarche_number,
        using_updated_since=using_updated_since,
        updated_since=updated_after,
    )


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
