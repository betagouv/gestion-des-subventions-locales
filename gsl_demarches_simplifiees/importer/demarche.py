from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.models import (
    Demarche,
    Dossier,
    FieldMappingForComputer,
    FieldMappingForHuman,
    Profile,
)


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


def save_demarche_from_ds(demarche_number):
    client = DsClient()
    result = client.get_demarche(demarche_number)
    demarche_data = result["data"]["demarche"]
    demarche = get_or_create_demarche(demarche_data)
    save_groupe_instructeurs(demarche_data, demarche)
    save_field_mappings(demarche_data, demarche)


def get_or_create_demarche(demarche_data):
    ds_fields = ("id", "number", "title", "state", "date_creation", "date_fermeture")
    django_data = {
        f"ds_{field}": demarche_data[camelcase(field)] for field in ds_fields
    }
    try:
        demarche = Demarche.objects.get(ds_id=demarche_data["id"])
        for field, value in django_data.items():
            demarche.__setattr__(field, value)
        demarche.save()
    except Demarche.DoesNotExist:
        demarche = Demarche.objects.create(**django_data)

    return demarche


def save_groupe_instructeurs(demarche_data, demarche):
    for groupe in demarche_data["groupeInstructeurs"]:
        for instructeur in groupe["instructeurs"]:
            instructeur, _ = Profile.objects.get_or_create(
                ds_id=instructeur["id"], ds_email=instructeur["email"]
            )
            demarche.ds_instructeurs.add(instructeur)


def save_field_mappings(demarche_data, demarche):
    reversed_mapping = {
        field.verbose_name: field.name for field in Dossier.MAPPED_FIELDS
    }
    for champ_descriptor in demarche_data["activeRevision"]["champDescriptors"]:
        ds_type = champ_descriptor["__typename"]
        if ds_type not in (
            "DropDownListChampDescriptor",
            "TextChampDescriptor",
            "TextareaChampDescriptor",
            "YesNoChampDescriptor",
            "SiretChampDescriptor",
            "PhoneChampDescriptor",
            "AddressChampDescriptor",
            "MultipleDropDownListChampDescriptor",
            "DecimalNumberChampDescriptor",
            "IntegerNumberChampDescriptor",
        ):
            continue
        ds_label = champ_descriptor["label"]
        ds_id = champ_descriptor["id"]
        qs_human_mapping = FieldMappingForHuman.objects.filter(label=ds_label)
        qs_computer_mapping = FieldMappingForComputer.objects.filter(
            ds_field_id=ds_id, demarche=demarche
        )
        if qs_computer_mapping.exists():
            continue
        if qs_human_mapping.exists():
            human_mapping = qs_human_mapping.get()
            if human_mapping.django_field:
                FieldMappingForComputer.objects.create(
                    ds_field_id=ds_id,
                    demarche=demarche,
                    ds_field_label=ds_label,
                    ds_field_type=ds_type,
                    django_field=human_mapping.django_field,
                    field_mapping_for_human=human_mapping,
                )
                continue
        if ds_label in reversed_mapping:
            FieldMappingForComputer.objects.create(
                ds_field_id=ds_id,
                demarche=demarche,
                ds_field_label=ds_label,
                ds_field_type=ds_type,
                django_field=reversed_mapping.get(ds_label),
            )
            continue
        if not qs_human_mapping.exists():
            FieldMappingForHuman.objects.create(
                label=ds_label,
                demarche=demarche,
            )
