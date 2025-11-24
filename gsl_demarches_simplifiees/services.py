from decimal import Decimal
from logging import getLogger
from typing import Callable, List, Literal

from django.core.exceptions import FieldDoesNotExist

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.exceptions import (
    DsServiceException,
    FieldError,
    InstructeurUnknown,
    UserRightsError,
)
from gsl_demarches_simplifiees.models import Dossier, FieldMappingForComputer
from gsl_projet.constants import DOTATION_DSIL, POSSIBLE_DOTATIONS

logger = getLogger(__name__)


class DsService:
    MUTATION_KEYS = {
        "checkbox": "dossierModifierAnnotationCheckbox",
        "decimal": "dossierModifierAnnotationDecimalNumber",
        "dismiss": "dossierClasserSansSuite",
    }

    MUTATION_FUNCTION = {
        "checkbox": "dossier_modifier_annotation_checkbox",
        "decimal": "dossier_modifier_annotation_decimal",
    }

    MUTATION_TYPES = Literal["checkbox", "decimal", "dismiss"]

    def __init__(self):
        self.mutator = DsMutator()

    # Status

    def dismiss_in_ds(self, dossier: Dossier, user: Collegue, motivation: str):
        instructeur_id = self._get_instructeur_id(user)
        results = self.mutator.dossier_classer_sans_suite(
            dossier.ds_id, instructeur_id, motivation
        )
        self._check_results(results, dossier, user, "dismiss", value=motivation)
        return results

    # Annotations

    def update_ds_is_in_qpv(self, dossier: Dossier, user: Collegue, value: bool):
        return self._update_boolean_field(dossier, user, value, "annotations_is_qpv")

    def update_ds_is_budget_vert(
        self, dossier: Dossier, user: Collegue, value: bool | str
    ):
        return self._update_boolean_field(
            dossier, user, bool(value), "annotations_is_budget_vert"
        )

    def update_ds_is_attached_to_a_crte(
        self, dossier: Dossier, user: Collegue, value: bool
    ):
        return self._update_boolean_field(dossier, user, value, "annotations_is_crte")

    def update_ds_assiette(
        self,
        dossier: Dossier,
        user: Collegue,
        dotation: POSSIBLE_DOTATIONS,
        value: float | None,
    ):
        return self._update_assiette_montant_or_taux(
            dossier, user, dotation, value, "assiette"
        )

    def update_ds_montant(
        self,
        dossier: Dossier,
        user: Collegue,
        dotation: POSSIBLE_DOTATIONS,
        value: float | None,
    ):
        return self._update_assiette_montant_or_taux(
            dossier, user, dotation, value, "montant_accorde"
        )

    def update_ds_taux(
        self,
        dossier: Dossier,
        user: Collegue,
        dotation: POSSIBLE_DOTATIONS,
        value: float | None,
    ):
        return self._update_assiette_montant_or_taux(
            dossier, user, dotation, value, "taux"
        )

    # Private

    def _update_assiette_montant_or_taux(
        self,
        dossier: Dossier,
        user: Collegue,
        dotation: POSSIBLE_DOTATIONS,
        value: float | None,
        field_name: str,
    ):
        suffix = "dsil" if dotation == DOTATION_DSIL else "detr"
        field = f"annotations_{field_name}_{suffix}"
        if value is None:
            value = 0
        return self._update_decimal_field(dossier, user, value, field)

    def _update_boolean_field(
        self, dossier: Dossier, user: Collegue, value: bool, field: str
    ):
        return self._update_annotation_field(dossier, user, value, field, "checkbox")

    def _update_decimal_field(
        self, dossier: Dossier, user: Collegue, value: float | Decimal, field: str
    ):
        return self._update_annotation_field(
            dossier, user, float(value), field, "decimal"
        )

    def _update_annotation_field(
        self,
        dossier: Dossier,
        user: Collegue,
        value: float | bool,
        field: str,
        mutation_type: MUTATION_TYPES,
    ):
        instructeur_id = self._get_instructeur_id(user)
        ds_field_id = self._get_ds_field_id(dossier, field)

        mutator_function_name = self.MUTATION_FUNCTION[mutation_type]

        mutator_function: Callable[[str, str, str, bool | float], dict] = getattr(
            self.mutator, mutator_function_name
        )
        results = mutator_function(dossier.ds_id, instructeur_id, ds_field_id, value)

        self._check_results(results, dossier, user, mutation_type, field, value)
        self._update_updated_at(dossier, results)
        return results

    def _update_updated_at(self, dossier: Dossier, results: dict):
        updated_at = results.get("data", {}).get("updatedAt")
        if updated_at:
            dossier.ds_date_derniere_modification = updated_at
            dossier.save(update_fields=["ds_date_derniere_modification"])

    def _get_instructeur_id(self, user: Collegue) -> str:
        instructeur_id = user.ds_id
        if bool(instructeur_id):
            return str(instructeur_id)

        raise InstructeurUnknown(extra={"user_id": user.id})

    def _get_ds_field_id(self, dossier: Dossier, field: str) -> str:
        try:
            ds_field = FieldMappingForComputer.objects.get(
                demarche=dossier.ds_demarche_id, django_field=field
            )
            return ds_field.ds_field_id

        except FieldMappingForComputer.DoesNotExist:
            field_name = field
            try:
                field_name = Dossier._meta.get_field(field).verbose_name
            except FieldDoesNotExist:
                pass

            raise FieldError(
                f'Le champ "{field_name}" n\'existe pas dans la démarche {dossier.ds_demarche.ds_number}.',
                extra={
                    "field_name": field_name,
                    "demarche_ds_number": dossier.ds_demarche.ds_number,
                    "dossier_ds_number": dossier.ds_number,
                },
            )

    def _check_results(
        self,
        results: dict,
        dossier: Dossier,
        user: Collegue,
        mutation_type: MUTATION_TYPES,
        field: str | None = None,
        value: float | bool | str | None = None,
    ) -> None:
        mutation_key = self.MUTATION_KEYS[mutation_type]
        data = results.get("data", None)

        if data is None or mutation_key in data and data.get(mutation_key) is None:
            if "errors" not in results.keys():
                return

            errors = results["errors"]
            messages = [error["message"] for error in errors]
            message = self._transform_message(messages)

            raise DsServiceException(
                message,
                log_message="Error in DS mutation",
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "user_id": user.id,
                    "mutation_key": mutation_key,
                    "field": field,
                    "value": value,
                    "error": messages,
                },
            )

        mutation_data = data.get(mutation_key)
        if "errors" not in mutation_data:
            return

        errors = mutation_data["errors"]
        if not bool(errors):
            return

        messages = [error["message"] for error in errors]
        if "L’instructeur n’a pas les droits d’accès à ce dossier" in messages:
            raise UserRightsError(
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "user_id": user.id,
                }
            )

        message = self._transform_message(messages)
        raise DsServiceException(
            message,
            log_message="Error in DS mutation",
            extra={
                "dossier_ds_number": dossier.ds_number,
                "user_id": user.id,
                "mutation_key": mutation_key,
                "field": field,
                "value": value,
                "error": messages,
            },
        )

    def _transform_message(self, messages: List[str]) -> str:
        new_messages = []
        for message in messages:
            if message == "Le dossier est déjà en\xa0construction":
                new_messages.append(
                    "Le dossier est en construction sur Démarches Simplifiées."
                )
            elif message == "An object of type Dossier was hidden due to permissions":
                new_messages.append("Vous n'avez pas accès à ce dossier.")
            else:
                new_messages.append(message)

        return ". ".join(new_messages)
