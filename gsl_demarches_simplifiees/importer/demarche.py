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
    "CheckboxChampDescriptor",
    "DateChampDescriptor",
    "DecimalNumberChampDescriptor",
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
    extract_categories_operation_detr(demarche_data, demarche)


def refresh_field_mappings_on_demarche(demarche_number):
    demarche = Demarche.objects.get(ds_number=demarche_number)
    if demarche.raw_ds_data:
        save_field_mappings(demarche.raw_ds_data, demarche)
        extract_categories_operation_detr(demarche.raw_ds_data, demarche)
    else:
        save_demarche_from_ds(demarche_number)


def refresh_categories_operation_detr(demarche_number):
    demarche = Demarche.objects.get(ds_number=demarche_number)
    if demarche.raw_ds_data:
        extract_categories_operation_detr(demarche.raw_ds_data, demarche)
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
        computer_mapping, created = FieldMappingForComputer.objects.get_or_create(
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

        if qs_human_mapping.exists():  # we have a label which is known
            human_mapping = qs_human_mapping.get()
            if human_mapping.django_field:
                computer_mapping.django_field = human_mapping.django_field
                computer_mapping.field_mapping_for_human = human_mapping
                computer_mapping.save()
                continue

        # Try direct mapping on verbose_name with original
        if ds_label in reversed_mapping:
            django_field = reversed_mapping.get(ds_label)
            if django_field != computer_mapping.django_field:
                computer_mapping.django_field = django_field
                computer_mapping.save()
                continue

        if not qs_human_mapping.exists() and not computer_mapping.django_field:
            FieldMappingForHuman.objects.create(label=ds_label, demarche=demarche)


def guess_department_from_demarche(demarche: Demarche) -> Departement:
    if demarche.perimetre and demarche.perimetre.departement:
        return demarche.perimetre.departement
    for departement in Departement.objects.all():
        if departement.name in demarche.ds_title:
            return departement


def guess_department_from_mapping(mapping: FieldMappingForComputer) -> Departement:
    # Essayons d'extraire le code département du libellé du champ.
    # Le libellé du champ DS est structuré de la façon suivante :
    # Catégories prioritaires (67 - Bas-Rhin)
    # On split la chaîne sur la parenthèse ouvrante et on récupère le 2e morceau,
    # puis on split le morceau sur " " et on récupère le premier morceau.
    departement_code = mapping.ds_field_label.split("(")[1].split(" ")[
        0
    ]  # todo gérer les erreurs
    try:
        return Departement.objects.filter(insee_code=departement_code)
    except Departement.DoesNotExist:
        pass
    # Sinon regardons si on trouve un département nommé dans le libellé du champ.
    for departement in Departement.objects.all():
        if departement.name in mapping.ds_field_label:
            return departement


def guess_year_from_demarche(demarche: Demarche) -> int:
    """
    Savoir à quelle année associer les catégories DETR extraites de la démarche DN
    """
    date_revision = demarche.active_revision_date
    if not date_revision:
        # à défaut de date de dernière révision,
        # on regarde la date de création de la démarche.
        date_revision = demarche.ds_date_creation

    if date_revision.month >= 9:
        return date_revision.year + 1
    else:
        return date_revision.year


def extract_categories_operation_detr(demarche_data: dict, demarche: Demarche):
    """
    Récupère toutes les valeurs possibles de catégorie DETR de la démarche DN,
    pour créer à la fois les gsl_projet.CategorieDetr
    et les gsl_demarches_simplifiees.CritereEligibiliteDetr nécessaires.
    :param demarche_data: le JSON brut de la démarche (avec champs, sans dossiers)
    :param demarche:  l'objet Django Demarche
    :return: rien
    """
    from gsl_projet.models import CategorieDetr

    try:
        # on cherche les correspondances techniques qui sont des "critères DETR"
        mappings = FieldMappingForComputer.objects.filter(
            demarche=demarche, django_field="demande_eligibilite_detr"
        ).all()
    except FieldMappingForComputer.DoesNotExist:
        return

    for mapping in mappings:
        demande_eligibilite_detr_field_id = mapping.ds_field_id

        options = []
        for field in demarche_data["activeRevision"]["champDescriptors"]:
            if field["id"] == demande_eligibilite_detr_field_id:
                options = field["options"]
                break

        departement = guess_department_from_mapping(mapping)
        # on pourrait aussi stocker le departement ou le périmètre sur le FieldMappingForComputer pour plus de robustesse.
        if not departement:
            return

        year = guess_year_from_demarche(
            demarche
        )  # voir comment on devine l'année (date de révision ?)
        if not year:
            return

        current_detr_category_ids = set()
        for sort_order, label in enumerate(options, 1):
            detr_cat, _ = CategorieDetr.objects.update_or_create(
                departement=departement,
                rang=sort_order,
                annee=year,
                defaults={"libelle": label, "is_current": True},
            )
            current_detr_category_ids.add(detr_cat.id)
            # si on restait dans l'idée de simplifier "méchamment", on enlèverait ceci :
            CritereEligibiliteDetr.objects.update_or_create(
                label=label,
                demarche=demarche,
                demarche_revision=demarche_data["activeRevision"]["id"],
                defaults={"detr_category": detr_cat},
            )
            # et il faudrait supprimer les contraintes d'unicité spécifiques à CritereEligibiliteDetr.
        # tout ce qui est dans le même département mais
        # n'est pas dans current_detr_categories :
        # on passe current à false
        CategorieDetr.objects.exclude(id__in=current_detr_category_ids).filter(
            departement=departement
        ).update(is_current=False)
