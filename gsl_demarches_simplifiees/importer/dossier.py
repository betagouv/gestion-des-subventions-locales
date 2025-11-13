import logging

from django.contrib import messages
from django.utils import timezone

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.models import Demarche, Dossier, Profile
from gsl_projet.services.projet_services import ProjetService

logger = logging.getLogger(__name__)


def save_demarche_dossiers_from_ds(demarche_number, using_updated_since: bool = True):
    new_updated_since = timezone.now()

    demarche = Demarche.objects.get(ds_number=demarche_number)
    client = DsClient()
    updated_since = demarche.updated_since if using_updated_since else None
    demarche_dossiers = client.get_demarche_dossiers(
        demarche_number, updated_since=updated_since
    )
    for i, dossier_data in enumerate(demarche_dossiers):
        ds_dossier_number = None

        try:
            ds_id = dossier_data["id"]
            ds_dossier_number = dossier_data["number"]
            dossier, _ = Dossier.objects.get_or_create(
                ds_id=ds_id,
                defaults={
                    "ds_demarche": demarche,
                    "ds_number": ds_dossier_number,
                },
            )
            _save_dossier_data_and_refresh_dossier_and_projet_and_co(
                dossier, dossier_data, async_refresh=True
            )
        except Exception as e:
            if not isinstance(e, DsServiceException):
                logger.exception(
                    "Error unhandled while saving dossier from DS",
                    extra={
                        "demarche_ds_number": demarche_number,
                        "dossier_ds_number": ds_dossier_number,
                        "error": str(e),
                        "i": i,
                    },
                )

    demarche.updated_since = new_updated_since
    demarche.save()


def save_one_dossier_from_ds(dossier: Dossier, client: DsClient | None = None):
    client = client or DsClient()
    dossier_data = client.get_one_dossier(dossier.ds_number)
    has_dossier_been_updated = _save_dossier_data_and_refresh_dossier_and_projet_and_co(
        dossier, dossier_data
    )

    if has_dossier_been_updated:
        return (
            messages.SUCCESS,
            "Le dossier a bien été mis à jour depuis Démarches Simplifiées.",
        )
    return (
        messages.WARNING,
        (
            "Le dossier était déjà à jour sur Turgot, nous ne l’avons pas "
            "remis à jour depuis Démarches Simplifiées."
        ),
    )


def _save_dossier_data_and_refresh_dossier_and_projet_and_co(
    dossier: Dossier, dossier_data: dict, async_refresh: bool = False
):
    has_dossier_been_updated = _has_dossier_been_updated_on_ds(dossier, dossier_data)
    refresh_dossier_instructeurs(dossier_data, dossier)
    dossier.raw_ds_data = dossier_data
    dossier.save()

    if has_dossier_been_updated:
        if async_refresh:
            from gsl_demarches_simplifiees.tasks import (
                task_refresh_dossier_from_saved_data,
            )

            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)
        else:
            refresh_dossier_from_saved_data(dossier)

    return has_dossier_been_updated


def _has_dossier_been_updated_on_ds(dossier: Dossier, dossier_data: dict) -> bool:
    date_modif_ds = dossier_data.get("dateDerniereModification", None)

    if not date_modif_ds:
        raise DsServiceException(
            "Une erreur est survenue lors de la mise à jour du dossier.",
            level=logging.ERROR,
            log_message="Unset date_modif_ds is not a normal situation.",
            extra={
                "dossier_ds_number": dossier.ds_number,
            },
        )

    if dossier.ds_date_derniere_modification is None:
        return True  # New dossier on Turgot

    date_modif_ds = timezone.datetime.fromisoformat(date_modif_ds)
    return date_modif_ds > dossier.ds_date_derniere_modification


def refresh_dossier_from_saved_data(dossier: Dossier):
    dossier_converter = DossierConverter(dossier.raw_ds_data, dossier)
    dossier_converter.fill_unmapped_fields()
    dossier_converter.convert_all_fields()
    dossier.save()

    ProjetService.create_or_update_projet_and_co_from_dossier(dossier.ds_number)

    # save_all_dates_from_dossier(dossier)


def refresh_dossier_instructeurs(dossier_data, dossier: Dossier):
    """
    Refreshes the instructeurs associated with a dossier based on data from Démarches Simplifiées.

    Assume ds_instructeur has been prefetch_related on dossier
    Noop if no changes, check only IDs does not check emails.
    """
    if "groupeInstructeur" not in dossier_data:
        # Should not happen except in tests
        return
    instructeurs_data = dossier_data["groupeInstructeur"]["instructeurs"]

    # Remove instructeurs that are not in the new data
    for profile in dossier.ds_instructeurs.all():
        if profile.ds_id not in (i["id"] for i in instructeurs_data):
            dossier.ds_instructeurs.remove(profile)

    # Add instructeurs that are not already in the dossier
    dossier_instructeurs_ids = [p.ds_id for p in dossier.ds_instructeurs.all()]
    for instructeur_data in instructeurs_data:
        if instructeur_data["id"] not in dossier_instructeurs_ids:
            instructeur, _ = Profile.objects.get_or_create(
                ds_id=instructeur_data["id"], ds_email=instructeur_data["email"]
            )
            dossier.ds_instructeurs.add(instructeur)


# def save_all_dates_from_dossier(dossier: Dossier):
#     dossier.ds_date_depot = dossier.raw_ds_data.get("dateDepot")
#     dossier.ds_date_passage_en_construction = dossier.raw_ds_data.get("datePassageEnConstruction")
#     dossier.ds_date_passage_en_instruction = dossier.raw_ds_data.get("datePassageEnInstruction")
#     dossier.ds_date_derniere_modification = dossier.raw_ds_data.get("dateDerniereModification")
#     dossier.ds_date_derniere_modification_champs = dossier.raw_ds_data.get("dateDerniereModificationChamps")
#     dossier.ds_date_traitement = dossier.raw_ds_data.get("dateTraitement")
#     dossier.save()
