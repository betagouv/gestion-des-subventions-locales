from django.utils import timezone

from gsl_core.models import Departement
from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.models import (
    CritereEligibiliteDetr,
    Demarche,
    Dossier,
    FieldMappingForComputer,
    FieldMappingForHuman,
    Profile,
)

IMPORTED_DS_FIELDS = (
    "AddressChampDescriptor",
    "DateChampDescriptor",
    "DecimalNumberChampDescriptor",
    "DropDownListChampDescriptor",
    "IntegerNumberChampDescriptor",
    "MultipleDropDownListChampDescriptor",
    "PhoneChampDescriptor",
    "SiretChampDescriptor",
    "TextChampDescriptor",
    "TextareaChampDescriptor",
    "YesNoChampDescriptor",
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
    extract_categories_operation_detr(demarche_data, demarche)


def refresh_field_mappings_on_demarche(demarche_number):
    demarche = Demarche.objects.get(ds_number=demarche_number)
    if demarche.raw_ds_data:
        save_field_mappings(demarche.raw_ds_data, demarche)
    else:
        save_demarche_from_ds(demarche_number)


def refresh_categories_operation_detr(demarche_number):
    demarche = Demarche.objects.get(ds_number=demarche_number)
    if demarche.raw_ds_data:
        extract_categories_operation_detr(demarche.raw_ds_data, demarche)
    else:
        save_demarche_from_ds(demarche_number)


def get_or_create_demarche(demarche_data):
    ds_fields = ("id", "number", "title", "state", "date_creation", "date_fermeture")
    django_data = {
        f"ds_{field}": demarche_data[camelcase(field)] for field in ds_fields
    }
    try:
        demarche = Demarche.objects.get(ds_id=demarche_data["id"])
        demarche.raw_ds_data = demarche_data
        for field, value in django_data.items():
            demarche.__setattr__(field, value)
        demarche.save()
    except Demarche.DoesNotExist:
        demarche = Demarche.objects.create(raw_ds_data=demarche_data, **django_data)

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
    for champ_descriptor in (
        demarche_data["activeRevision"]["champDescriptors"]
        + demarche_data["activeRevision"]["annotationDescriptors"]
    ):
        ds_type = champ_descriptor["__typename"]
        if ds_type not in IMPORTED_DS_FIELDS:
            continue
        ds_label = champ_descriptor["label"]
        ds_id = champ_descriptor["id"]
        qs_human_mapping = FieldMappingForHuman.objects.filter(label=ds_label)
        computer_mapping, _ = FieldMappingForComputer.objects.get_or_create(
            ds_field_id=ds_id,
            demarche=demarche,
            defaults={
                "ds_field_label": ds_label,
                "ds_field_type": ds_type,
            },
        )
        if computer_mapping.django_field:  # field is already mapped, continue
            continue
        if qs_human_mapping.exists():  # we have a label which is known
            human_mapping = qs_human_mapping.get()
            if human_mapping.django_field:
                computer_mapping.django_field = human_mapping.django_field
                computer_mapping.field_mapping_for_human = human_mapping
                computer_mapping.save()
                continue
        if ds_label in reversed_mapping:
            computer_mapping.django_field = reversed_mapping.get(ds_label)
            computer_mapping.save()
            continue
        if not qs_human_mapping.exists():
            FieldMappingForHuman.objects.create(
                label=ds_label,
                demarche=demarche,
            )


def guess_department_from_demarche(demarche) -> Departement:
    for departement in Departement.objects.all():
        if departement.name in demarche.ds_title:
            return departement


def guess_year_from_demarche_data(demarche_data) -> int:
    """
    Savoir à quelle année associer les catégories DETR extraites de la démarche DS
    """
    date_revision = demarche_data["activeRevision"]["datePublication"]
    if not date_revision:
        # à défaut de date de dernière révision,
        # on regarde la date de création de la démarche.
        date_revision = demarche_data["dateCreation"]
    date = timezone.datetime.fromisoformat(date_revision)
    if not date:
        return

    if date.month >= 9:
        return date.year + 1
    else:
        return date.year


def extract_categories_operation_detr(demarche_data, demarche: Demarche):
    from gsl_projet.models import CategorieDetr

    try:
        mapping = FieldMappingForComputer.objects.filter(
            demarche=demarche, django_field="demande_eligibilite_detr"
        ).get()
    except FieldMappingForComputer.DoesNotExist:
        return
    demande_eligibilite_detr_field_id = mapping.ds_field_id

    options = []
    for field in demarche_data["activeRevision"]["champDescriptors"]:
        if field["id"] == demande_eligibilite_detr_field_id:
            options = field["options"]
            break

    departement = guess_department_from_demarche(demarche)
    if not departement:
        return

    year = guess_year_from_demarche_data(demarche_data)
    if not year:
        return

    for sort_order, label in enumerate(options):
        detr_cat, _ = CategorieDetr.objects.get_or_create(
            departement=departement,
            tri=sort_order,
            annee=2025,
            defaults={"libelle": label},
        )
        CritereEligibiliteDetr.objects.update_or_create(
            label=label,
            demarche=demarche,
            demarche_revision=demarche_data["activeRevision"]["id"],
            defaults={"detr_category": detr_cat},
        )
