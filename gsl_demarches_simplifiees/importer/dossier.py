from django.db import models

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.models import Demarche, Dossier, FieldMappingForComputer


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


def save_demarche_dossiers_from_ds(demarche_number):
    client = DsClient()
    for dossier_data in client.get_demarche_dossiers(demarche_number):
        ds_id = dossier_data["id"]
        dossier = get_or_create_dossier(ds_id, demarche_number)

        django_data = extract_django_data(dossier_data)

        for field, value in django_data.items():
            dossier.__setattr__(field, value)

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


def extract_django_data(dossier_data):
    django_data = {
        f"ds_{field}": dossier_data[camelcase(field)]
        for field in (
            "number",
            "state",
            "date_depot",
            "date_passage_en_construction",
            "date_passage_en_instruction",
            "date_derniere_modification_champs",
        )
    }

    ds_field_ids = tuple(champ["id"] for champ in dossier_data["champs"])

    computed_mappings = FieldMappingForComputer.objects.filter(
        ds_field_id__in=ds_field_ids
    ).exclude(django_field="")

    ds_id_to_django_field = {
        mapping.ds_field_id: Dossier._meta.get_field(mapping.django_field)
        for mapping in computed_mappings.all()
    }

    for champ in dossier_data["champs"]:
        ds_champ_id = champ["id"]
        if ds_champ_id in ds_id_to_django_field:
            django_field = ds_id_to_django_field[ds_champ_id]
            if isinstance(django_field, models.CharField):
                ds_field_value = champ["stringValue"]
                django_data[django_field.name] = ds_field_value

    return django_data
