from logging import getLogger

from django.utils import timezone

from gsl_core.models import Departement
from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.importer.utils import get_departement_from_field_label
from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    CategorieDsil,
    Demarche,
    Dossier,
    FieldMapping,
    Profile,
)

logger = getLogger(__name__)

IMPORTED_DS_FIELDS = (
    "AddressChampDescriptor",
    "CheckboxChampDescriptor",
    "DateChampDescriptor",
    "DecimalNumberChampDescriptor",
    "DossierLinkChampDescriptor",
    "DropDownListChampDescriptor",
    "IntegerNumberChampDescriptor",
    "LinkedDropDownListChampDescriptor",
    "MultipleDropDownListChampDescriptor",
    "PhoneChampDescriptor",
    "SiretChampDescriptor",
    "TextareaChampDescriptor",
    "TextChampDescriptor",
    "YesNoChampDescriptor",
)


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


def save_demarche_from_ds(
    demarche_number, refresh_only_if_demarche_has_been_updated=False
):
    client = DsClient()
    result = client.get_demarche(demarche_number)
    demarche_data = result["data"]["demarche"]

    if refresh_only_if_demarche_has_been_updated:
        try:
            demarche = Demarche.objects.get(ds_number=demarche_number)
            if demarche.active_revision_id == demarche_data["activeRevision"]["id"]:
                return
        except Demarche.DoesNotExist:
            pass

    demarche = update_or_create_demarche(demarche_data)
    save_groupe_instructeurs(demarche_data, demarche)
    save_field_mappings(demarche_data, demarche)
    save_categories_detr(demarche_data, demarche)
    save_categories_dsil(demarche_data, demarche)


def refresh_field_mappings_on_demarche(demarche_number):
    demarche = Demarche.objects.get(ds_number=demarche_number)
    if demarche.raw_ds_data:
        save_field_mappings(demarche.raw_ds_data, demarche)
        save_categories_detr(demarche.raw_ds_data, demarche)
        save_categories_dsil(demarche.raw_ds_data, demarche)
    else:
        save_demarche_from_ds(demarche_number)


def update_or_create_demarche(demarche_data):
    ds_fields = ("id", "number", "title", "state", "date_creation", "date_fermeture")
    django_data = {
        f"ds_{field}": demarche_data[camelcase(field)] for field in ds_fields
    }
    if demarche_data["activeRevision"]:
        active_revision_date = demarche_data["activeRevision"]["datePublication"]
        django_data["active_revision_date"] = (
            None
            if active_revision_date is None
            else timezone.datetime.fromisoformat(active_revision_date)
        )
        django_data["active_revision_id"] = demarche_data["activeRevision"]["id"]
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


DN_DEPARTEMENT_FIELD_TO_DJANGO_FIELD_MAP = {
    "Catégories prioritaires": "demande_categorie_detr",
    "Arrondissement du demandeur": "porteur_de_projet_arrondissement",
}


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
        computer_mapping, created = FieldMapping.objects.get_or_create(
            ds_field_id=ds_id,
            demarche=demarche,
            defaults={
                "ds_field_label": ds_label,
                "ds_field_type": ds_type,
            },
        )

        if not created:
            if (
                computer_mapping.ds_field_label != ds_label
                or computer_mapping.ds_field_type != ds_type
            ):
                computer_mapping.ds_field_label = ds_label
                computer_mapping.ds_field_type = ds_type
                computer_mapping.save()

        if ds_label in reversed_mapping:
            django_field = reversed_mapping.get(ds_label)
            if django_field != computer_mapping.django_field:
                computer_mapping.django_field = django_field
                computer_mapping.save()
                continue

        for dn_field, django_field in DN_DEPARTEMENT_FIELD_TO_DJANGO_FIELD_MAP.items():
            if ds_label.startswith(dn_field):
                computer_mapping.django_field = django_field
                computer_mapping.save()
                break


def save_categories_dsil(demarche_data, demarche):
    mapping = FieldMapping.objects.get(
        demarche=demarche, django_field="demande_categorie_dsil"
    )
    demande_categorie_dsil_field_id = mapping.ds_field_id
    options = []
    for field in demarche_data["activeRevision"]["champDescriptors"]:
        if field["id"] == demande_categorie_dsil_field_id:
            options = field["options"]
            break
    categories = []
    for sort_order, label in enumerate(options, 1):
        category, _ = CategorieDsil.objects.update_or_create(
            demarche=demarche,
            label=label,
            defaults={"rank": sort_order, "active": True, "deactivated_at": None},
        )
        categories.append(category)

    CategorieDsil.objects.filter(demarche=demarche, active=True).exclude(
        id__in=[category.id for category in categories]
    ).update(active=False, deactivated_at=timezone.now())


def save_categories_detr(demarche_data: dict, demarche: Demarche) -> None:
    field_mappings = FieldMapping.objects.filter(
        demarche=demarche, django_field="demande_categorie_detr"
    )
    for field in demarche_data["activeRevision"]["champDescriptors"]:
        if "Catégories prioritaires " not in field["label"]:
            continue

        try:
            field_mapping = field_mappings.get(ds_field_label=field["label"])
        except FieldMapping.DoesNotExist:
            logger.info("No field mapping found for field %s", field["label"])
            continue

        _save_categorie_detr_from_field(field, field_mapping, demarche)


def _save_categorie_detr_from_field(
    field: dict, field_mapping: FieldMapping, demarche: Demarche
) -> None:
    departement = _get_departement_from_field_mapping(field_mapping)
    if not departement:
        logger.info(
            f"No departement found for field mapping (#{field_mapping.id} - {field_mapping.ds_field_label})"
        )
        return

    options = field["options"]
    categories = []
    parent_label = ""
    for sort_order, label in enumerate(options, 1):
        if label.startswith("--"):
            parent_label = label.strip("--")

            next_option = options[sort_order] if sort_order < len(options) else None
            is_next_option_a_parent = next_option is None or next_option.startswith(
                "--"
            )
            if not is_next_option_a_parent:
                continue

            label = parent_label
            parent_label = ""

        category, _ = CategorieDetr.objects.update_or_create(
            demarche=demarche,
            label=label,
            departement=departement,
            defaults={
                "rank": sort_order,
                "active": True,
                "deactivated_at": None,
                "parent_label": parent_label,
            },
        )
        categories.append(category)

    CategorieDetr.objects.filter(
        demarche=demarche, departement=departement, active=True
    ).exclude(id__in=[category.id for category in categories]).update(
        active=False, deactivated_at=timezone.now()
    )


def _get_departement_from_field_mapping(field_mapping) -> Departement | None:
    label = getattr(field_mapping, "ds_field_label", "") or ""
    try:
        return get_departement_from_field_label(label)
    except ValueError:
        return None
