from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.models import Demarche, Dossier


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


def save_demarche_dossiers_from_ds(demarche_number):
    client = DsClient()
    for dossier_data in client.get_demarche_dossiers(demarche_number):
        ds_id = dossier_data["id"]
        dossier = get_or_create_dossier(ds_id, demarche_number)

        try:
            dossier.save()
        except Exception as e:
            print(e)


def get_or_create_dossier(ds_dossier_id, demarche_number):
    dossier_qs = Dossier.objects.filter(ds_id=ds_dossier_id)
    if dossier_qs.exists():
        return dossier_qs.get()
    demarche = Demarche.objects.get(ds_number=demarche_number)
    return Dossier(ds_id=ds_dossier_id, ds_demarche=demarche)


"""
    for champ in dossier_data["champs"]:
        ds_champ_id = champ["id"]
        if ds_champ_id in ds_id_to_django_field:
            django_field = ds_id_to_django_field[ds_champ_id]
            if isinstance(django_field, models.CharField):
                ds_field_value = champ["stringValue"]
                django_data[django_field.name] = ds_field_value

    return django_data
"""
