import datetime
from collections.abc import Iterable

from django.db import models

from gsl_demarches_simplifiees.models import (
    Dossier,
    DsChoiceLibelle,
    FieldMappingForComputer,
)


class DossierConverter:
    def __init__(self, ds_dossier_data: dict, dossier: Dossier):
        self.ds_field_ids = tuple(champ["id"] for champ in ds_dossier_data["champs"])
        self.ds_fields_by_id = {
            champ["id"]: champ for champ in ds_dossier_data["champs"]
        }
        self.computed_mappings = FieldMappingForComputer.objects.filter(
            ds_field_id__in=self.ds_field_ids
        ).exclude(django_field="")

        self.ds_id_to_django_field = {
            mapping.ds_field_id: Dossier._meta.get_field(mapping.django_field)
            for mapping in self.computed_mappings.all()
        }

        self.dossier = dossier

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

        if ds_typename == "TextChamp":
            return ds_field_data["stringValue"]

        if ds_typename == "DecimalNumberChamp":
            return ds_field_data["decimalNumber"]

        if ds_typename == "MultipleDropDownListChamp":
            return ds_field_data["values"]

        if ds_typename == "DateChamp":
            return datetime.date(*(int(s) for s in ds_field_data["date"].split("-")))

        raise NotImplementedError(
            f"DS Fields of type '{ds_typename}' are not supported"
        )

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
            if not issubclass(django_field_object.related_model, DsChoiceLibelle):
                raise NotImplementedError("Can only inject DsChoiceLibelle objects")
            injectable_value, _ = (
                django_field_object.related_model.objects.get_or_create(
                    label=injectable_value
                )
            )

        dossier.__setattr__(django_field_object.name, injectable_value)
