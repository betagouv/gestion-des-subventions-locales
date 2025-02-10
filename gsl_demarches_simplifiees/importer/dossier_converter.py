import datetime
from collections.abc import Iterable
from itertools import chain

from django.db import models

from gsl_core.models import Adresse
from gsl_demarches_simplifiees.models import (
    Dossier,
    DsChoiceLibelle,
    FieldMappingForComputer,
    PersonneMorale,
)


def camelcase(my_string):
    s = my_string.title().replace("_", "")
    return f"{s[0].lower()}{s[1:]}"


class DossierConverter:
    UNMAPPED_FIELDS = (
        "state",
        "date_depot",
        "date_derniere_modification",
        "date_passage_en_construction",
        "date_passage_en_instruction",
        "date_derniere_modification_champs",
        "date_traitement",
    )

    def __init__(self, ds_dossier_data: dict, dossier: Dossier):
        self.ds_fields_by_id = {
            champ["id"]: champ
            for champ in chain(
                ds_dossier_data["champs"], ds_dossier_data["annotations"]
            )
        }
        computed_mappings = FieldMappingForComputer.objects.filter(
            ds_field_id__in=self.ds_fields_by_id.keys()
        ).exclude(django_field="")

        self.ds_dossier_data = ds_dossier_data

        self.ds_id_to_django_field = {
            mapping.ds_field_id: Dossier._meta.get_field(mapping.django_field)
            for mapping in computed_mappings.all()
        }

        self.dossier = dossier
        self.dossier.raw_ds_data = ds_dossier_data

    def fill_unmapped_fields(self):
        for field in self.UNMAPPED_FIELDS:
            django_field = f"ds_{field}"
            ds_key = camelcase(field)
            self.dossier.__setattr__(django_field, self.ds_dossier_data[ds_key])
        # deal with "demandeur" differently
        demandeur_data = self.ds_dossier_data.get("demandeur")
        if not demandeur_data:
            return

        demandeur = self.dossier.ds_demandeur
        if not demandeur:
            demandeur, _ = PersonneMorale.objects.get_or_create(
                siret=demandeur_data.get("siret")
            )
        demandeur.update_from_raw_ds_data(demandeur_data)
        demandeur.save()
        self.dossier.ds_demandeur = demandeur

    def convert_all_fields(self):
        for ds_field_id in self.ds_id_to_django_field:
            ds_field_data = self.ds_fields_by_id[ds_field_id]
            django_field_object = self.ds_id_to_django_field[ds_field_id]
            self.convert_one_field(ds_field_data, django_field_object)

    def convert_one_field(self, ds_field_data, django_field_object):
        """
        :param ds_field_id:
        :return:
        """
        try:
            injectable_value = self.extract_ds_data(ds_field_data)
            self.inject_into_field(self.dossier, django_field_object, injectable_value)
        except NotImplementedError as e:
            print(e)

    def extract_ds_data(self, ds_field_data):
        ds_typename = ds_field_data["__typename"]

        if ds_typename == "CheckboxChamp":
            return ds_field_data["checked"]

        if ds_typename in ("TextChamp", "SiretChamp"):
            return ds_field_data["stringValue"]

        if ds_typename == "DecimalNumberChamp":
            return ds_field_data["decimalNumber"]

        if ds_typename == "IntegerNumberChamp":
            return int(ds_field_data["integerNumber"])

        if ds_typename == "MultipleDropDownListChamp":
            return ds_field_data["values"]

        if ds_typename == "AddressChamp":
            return ds_field_data["address"] or ds_field_data["stringValue"]

        if ds_typename == "DateChamp":
            return datetime.date(*(int(s) for s in ds_field_data["date"].split("-")))

        raise NotImplementedError(
            f"DS Fields of type '{ds_typename}' are not supported"
        )

    def _prepare_address_for_injection(
        self, dossier: Dossier, django_field_object: models.Field, injectable_value
    ):
        adresse = dossier.__getattribute__(django_field_object.name) or Adresse()
        adresse.update_from_raw_ds_data(injectable_value)
        adresse.save()
        return adresse

    def inject_into_field(
        self, dossier: Dossier, django_field_object: models.Field, injectable_value
    ):
        if isinstance(django_field_object, models.ManyToManyField):
            if not isinstance(injectable_value, Iterable):
                injectable_value = [injectable_value]
            if not issubclass(django_field_object.related_model, DsChoiceLibelle):
                raise NotImplementedError("Can only inject DsChoiceLibelle objects")

            for value in injectable_value:
                related, _ = django_field_object.related_model.objects.get_or_create(
                    label=value
                )
                dossier.__getattribute__(django_field_object.name).add(related)

            return

        if isinstance(django_field_object, models.ForeignKey):
            if issubclass(django_field_object.related_model, Adresse):
                injectable_value = self._prepare_address_for_injection(
                    dossier, django_field_object, injectable_value
                )

            elif not issubclass(django_field_object.related_model, DsChoiceLibelle):
                raise NotImplementedError("Can only inject DsChoiceLibelle objects")
            else:
                injectable_value, _ = (
                    django_field_object.related_model.objects.get_or_create(
                        label=injectable_value
                    )
                )

        dossier.__setattr__(django_field_object.name, injectable_value)
