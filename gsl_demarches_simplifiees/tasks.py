from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.models import Demarche


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


def save_demarche_from_ds(demarche_number):
    client = DsClient()
    result = client.get_demarche(demarche_number)
    demarche_data = result["data"]["demarche"]
    ds_fields = ("id", "number", "title", "state", "date_creation", "date_fermeture")
    django_data = {
        f"ds_{field}": demarche_data[camelcase(field)] for field in ds_fields
    }
    try:
        demarche = Demarche.objects.get(ds_id=demarche_data["id"])
        for field, value in django_data:
            demarche.__setattr__(field, value)
        demarche.save()
    except Demarche.DoesNotExist:
        print(demarche_data)
        demarche = Demarche.objects.create(**django_data)
