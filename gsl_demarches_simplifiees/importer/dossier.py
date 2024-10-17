from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.models import Demarche, Dossier


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


def save_demarche_dossiers_from_ds(demarche_number):
    client = DsClient()
    for dossier_data in client.get_demarche_dossiers(demarche_number):
        ds_id = dossier_data["id"]
        ds_dossier_number = dossier_data["number"]
        dossier = get_or_create_dossier(ds_id, ds_dossier_number, demarche_number)

        try:
            dossier.save()
        except Exception as e:
            print(e)


def get_or_create_dossier(ds_dossier_id, ds_dossier_number, demarche_number):
    dossier_qs = Dossier.objects.filter(ds_id=ds_dossier_id)
    if dossier_qs.exists():
        return dossier_qs.get()
    demarche = Demarche.objects.get(ds_number=demarche_number)
    return Dossier.objects.create(
        ds_id=ds_dossier_id, ds_demarche=demarche, ds_number=ds_dossier_number
    )
