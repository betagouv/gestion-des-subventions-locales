import datetime
from collections.abc import Iterable
from itertools import chain
from logging import getLogger

from django.db import models

from gsl_core.models import Adresse, Arrondissement, Departement
from gsl_demarches_simplifiees.models import (
    Dossier,
    DsChoiceLibelle,
    FieldMappingForComputer,
    PersonneMorale,
)

logger = getLogger(__name__)


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
        self.ds_demarche_revision = ds_dossier_data["demarche"]["revision"]["id"]
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
            try:
                return int(ds_field_data["integerNumber"])
            except TypeError:
                logger.warning(
                    "Value of IntegerNumberChamp is uncorrect.",
                    extra={"value": ds_field_data["integerNumber"]},
                )
                return None

        if ds_typename == "MultipleDropDownListChamp":
            return ds_field_data["values"]

        if ds_typename == "LinkedDropDownListChamp":
            return ds_field_data["secondaryValue"]

        if ds_typename == "AddressChamp":
            return ds_field_data["address"] or ds_field_data["stringValue"]

        if ds_typename == "DateChamp":
            return datetime.date(*(int(s) for s in ds_field_data["date"].split("-")))

        raise NotImplementedError(
            f"DS Fields of type '{ds_typename}' are not supported"
        )

    def inject_into_field(
        self, dossier: Dossier, django_field_object: models.Field, injectable_value
    ):
        if isinstance(django_field_object, models.ManyToManyField):
            if isinstance(injectable_value, str) or not isinstance(
                injectable_value, Iterable
            ):
                injectable_value = [injectable_value]
            if not issubclass(django_field_object.related_model, DsChoiceLibelle):
                raise NotImplementedError("Can only inject DsChoiceLibelle objects")

            for value in injectable_value:
                related, _ = django_field_object.related_model.objects.get_or_create(
                    **self._get_related_model_get_or_create_arguments(
                        django_field_object.related_model, value
                    )
                )
                dossier.__getattribute__(django_field_object.name).add(related)

            return

        if isinstance(django_field_object, models.ForeignKey):
            if issubclass(django_field_object.related_model, Adresse):
                injectable_value = self._prepare_address_for_injection(
                    dossier, django_field_object, injectable_value
                )
            if issubclass(django_field_object.related_model, Departement):
                injectable_value = self._prepare_departement_for_injection(
                    dossier, django_field_object, injectable_value
                )
            if issubclass(django_field_object.related_model, Arrondissement):
                injectable_value = self._prepare_arrondissement_for_injection(
                    dossier, django_field_object, injectable_value
                )

            elif not issubclass(django_field_object.related_model, DsChoiceLibelle):
                raise NotImplementedError("Can only inject DsChoiceLibelle objects")
            else:
                injectable_value, _ = (
                    django_field_object.related_model.objects.get_or_create(
                        **self._get_related_model_get_or_create_arguments(
                            django_field_object.related_model, injectable_value
                        )
                    )
                )

        dossier.__setattr__(django_field_object.name, injectable_value)

    def _prepare_address_for_injection(
        self, dossier: Dossier, django_field_object: models.Field, injectable_value
    ):
        adresse = dossier.__getattribute__(django_field_object.name) or Adresse()
        adresse.update_from_raw_ds_data(injectable_value)
        adresse.save()
        return adresse

    def _prepare_departement_for_injection(
        self, dossier: Dossier, django_field_object: models.Field, injectable_value
    ) -> Departement | None:
        """
        Extrait le code INSEE du format "04 - Alpes-de-Haute-Provence"
        et récupère le département correspondant.
        Le code peut être de 2 ou 3 caractères (ex: 01, 981).
        """
        if not injectable_value:
            return None

        # Extraire le code INSEE (les caractères avant " - ")
        # Format attendu: "04 - Alpes-de-Haute-Provence"
        if " - " in injectable_value:
            code_insee = injectable_value.split(" - ")[0].strip()
        else:
            # Si le format n'est pas celui attendu, on essaie de prendre les 2-3 premiers caractères
            code_insee = injectable_value[:3].strip()

        # Récupérer le département par son code INSEE
        try:
            departement = Departement.objects.get(insee_code=code_insee)
            return departement
        except Departement.DoesNotExist:
            logger.warning(
                f"Département avec le code INSEE '{code_insee}' non trouvé",
                extra={
                    "dossier_ds_number": self.dossier.ds_number,
                    "injectable_value": injectable_value,
                    "code_insee": code_insee,
                },
            )
            return None

    def _prepare_arrondissement_for_injection(
        self, dossier: Dossier, django_field_object: models.Field, injectable_value
    ) -> Arrondissement | None:
        """
        Extrait le nom de l'arrondissement du format "04 - Alpes-de-Haute-Provence - arrondissement de Barcelonnette"
        et récupère l'arrondissement correspondant.
        """
        if not injectable_value:
            return None

        # Format attendu: "04 - Alpes-de-Haute-Provence - arrondissement de Barcelonnette"
        parts = injectable_value.split(" - ")

        if len(parts) < 3:
            logger.warning(
                f"Format d'arrondissement invalide: '{injectable_value}'",
                extra={
                    "dossier_ds_number": self.dossier.ds_number,
                    "injectable_value": injectable_value,
                },
            )
            return None

        # Extraire le code du département (première partie)
        code_departement = parts[0].strip()

        # Extraire le nom de l'arrondissement (dernière partie après "arrondissement de ")
        arrondissement_part = parts[2].strip()
        if arrondissement_part.startswith("arrondissement de "):
            nom_arrondissement = arrondissement_part.replace(
                "arrondissement de ", ""
            ).strip()
        else:
            # Si le format est différent, on prend la dernière partie
            nom_arrondissement = arrondissement_part

        # Récupérer le département
        try:
            departement = Departement.objects.get(insee_code=code_departement)
        except Departement.DoesNotExist:
            logger.warning(
                f"Département avec le code INSEE '{code_departement}' non trouvé pour l'arrondissement",
                extra={
                    "dossier_ds_number": self.dossier.ds_number,
                    "injectable_value": injectable_value,
                    "code_departement": code_departement,
                },
            )
            return None

        # Récupérer l'arrondissement par son nom dans ce département
        try:
            arrondissement = Arrondissement.objects.get(
                name=nom_arrondissement, departement=departement
            )
            return arrondissement
        except Arrondissement.DoesNotExist:
            logger.warning(
                f"Arrondissement '{nom_arrondissement}' non trouvé dans le département {code_departement}",
                extra={
                    "dossier_ds_number": self.dossier.ds_number,
                    "injectable_value": injectable_value,
                    "nom_arrondissement": nom_arrondissement,
                    "code_departement": code_departement,
                },
            )
            return None
        except Arrondissement.MultipleObjectsReturned:
            logger.warning(
                f"Plusieurs arrondissements '{nom_arrondissement}' trouvés dans le département {code_departement}",
                extra={
                    "dossier_ds_number": self.dossier.ds_number,
                    "injectable_value": injectable_value,
                    "nom_arrondissement": nom_arrondissement,
                    "code_departement": code_departement,
                },
            )
            # En cas de doublon, on prend le premier
            return Arrondissement.objects.filter(
                name=nom_arrondissement, departement=departement
            ).first()

    def _get_related_model_get_or_create_arguments(
        self, related_model, injectable_value
    ):
        arguments = {"label": injectable_value}
        for constraint in related_model._meta.constraints:
            if isinstance(constraint, models.UniqueConstraint):
                fields = constraint.fields
                if "demarche" in fields and "demarche_revision" in fields:
                    arguments["demarche"] = self.dossier.ds_demarche
                    arguments["demarche_revision"] = self.ds_demarche_revision
        return arguments
