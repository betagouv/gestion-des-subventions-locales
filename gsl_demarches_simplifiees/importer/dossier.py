import logging

from django.contrib import messages
from django.utils import timezone

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.models import Demarche, Dossier, Profile
from gsl_projet.tasks import create_or_update_projet_and_co_from_dossier


def save_demarche_dossiers_from_ds(demarche_number):
    from gsl_demarches_simplifiees.tasks import task_refresh_dossier_from_saved_data

    client = DsClient()
    demarche_dossiers = client.get_demarche_dossiers(demarche_number)
    for i, dossier_data in enumerate(demarche_dossiers):
        try:
            ds_id = dossier_data["id"]
            ds_dossier_number = dossier_data["number"]
            dossier = get_or_create_dossier(
                ds_id, ds_dossier_number, demarche_number, dossier_data
            )
            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)
        except Exception as e:
            logging.error(
                f"Erreur pour le {i}ème dossier de la démarche {demarche_number}",
                str(e),
            )


def save_one_dossier_from_ds(dossier: Dossier, client: DsClient | None = None):
    client = client or DsClient()
    dossier_data = client.get_one_dossier(dossier.ds_number)
    refresh_dossier_instructeurs(dossier_data, dossier)
    date_modif_ds = dossier_data.get("dateDerniereModification", None)
    if date_modif_ds:
        date_modif_ds = timezone.datetime.fromisoformat(date_modif_ds)
        if date_modif_ds > dossier.ds_date_derniere_modification:
            dossier.raw_ds_data = dossier_data
            refresh_dossier_from_saved_data(dossier)
            return (
                messages.SUCCESS,
                "Le dossier a bien été mis à jour depuis Démarches Simplifiées.",
            )
        else:
            return (
                messages.WARNING,
                (
                    "Le dossier était déjà à jour sur Turgot, nous ne l’avons pas "
                    "remis à jour depuis Démarches Simplifiées."
                ),
            )

    raise DsServiceException("Unset date_modif_ds is not a normal situation.")


def refresh_dossier_from_saved_data(dossier: Dossier):
    dossier_converter = DossierConverter(dossier.raw_ds_data, dossier)
    dossier_converter.fill_unmapped_fields()
    dossier_converter.convert_all_fields()
    try:
        dossier.save()
    except Exception as e:
        logging.error(
            str(e),
        )
        raise e

    create_or_update_projet_and_co_from_dossier(dossier.ds_number)


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


def get_or_create_dossier(ds_dossier_id, ds_dossier_number, demarche_number, raw_data):
    dossier_qs = Dossier.objects.filter(ds_id=ds_dossier_id)
    if dossier_qs.exists():
        dossier = dossier_qs.get()
        dossier.raw_ds_data = raw_data
        dossier.save()
        return dossier
    demarche = Demarche.objects.get(ds_number=demarche_number)
    return Dossier.objects.create(
        ds_id=ds_dossier_id,
        ds_demarche=demarche,
        ds_number=ds_dossier_number,
        raw_ds_data=raw_data,
    )
