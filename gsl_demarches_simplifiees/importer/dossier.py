import logging

from celery import shared_task

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.importer.dossier_converter import DossierConverter
from gsl_demarches_simplifiees.models import Demarche, Dossier


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


def save_demarche_dossiers_from_ds(demarche_number):
    client = DsClient()
    demarche_dossiers = client.get_demarche_dossiers(demarche_number)
    i = 1
    for dossier_data in demarche_dossiers:
        try:
            ds_id = dossier_data["id"]
            ds_dossier_number = dossier_data["number"]
            dossier = get_or_create_dossier(
                ds_id, ds_dossier_number, demarche_number, dossier_data
            )
            dossier.save()
            refresh_dossier_from_saved_data.delay(dossier.ds_number)
            i += 1
        except Exception as e:
            logging.error(
                f"Erreur pour le {i}ème dossier de la démarche {demarche_number}",
                str(e),
            )


@shared_task
def refresh_dossier_from_saved_data(dossier_ds_number):
    dossier = Dossier.objects.get(ds_number=dossier_ds_number)
    dossier_converter = DossierConverter(dossier.raw_ds_data, dossier)
    dossier_converter.fill_unmapped_fields()
    dossier_converter.convert_all_fields()
    try:
        dossier.save()
    except Exception as e:
        print(e)


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
