import logging

from django.contrib import messages
from django.utils import timezone

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.models import Demarche, Dossier


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


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
            dossier.save()
            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)
        except Exception as e:
            logging.error(
                f"Erreur pour le {i}ème dossier de la démarche {demarche_number}",
                str(e),
            )


def save_one_dossier_from_ds(dossier: Dossier, client: DsClient = None):
    client = client or DsClient()
    dossier_data = client.get_one_dossier(dossier.ds_number)
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
