from datetime import datetime
from logging import getLogger
from typing import List, Literal

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
        "dismiss": "dossierClasserSansSuite",
        "annotations": "dossierModifierAnnotations",
        "passer_en_instruction": "dossierPasserEnInstruction",
    }

    MUTATION_TYPES = Literal["dismiss", "annotations"]

    def __init__(self):
        self.mutator = DsMutator()

    # Status

    def passer_en_instruction(self, dossier: Dossier, user: Collegue):
        results = self.mutator.dossier_passer_en_instruction(dossier.ds_id, user.ds_id)
        self._check_results(results, dossier, user, "passer_en_instruction")
        dossier.ds_state = Dossier.STATE_EN_INSTRUCTION
        date_derniere_modification = (
            results.get("data", {})
            .get("dossierPasserEnInstruction")
            .get("dossier")
            .get("dateDerniereModification")
        )
        dossier.ds_date_derniere_modification = (
            datetime.fromisoformat(date_derniere_modification)
            if date_derniere_modification
            else None
        )
        dossier.save()
        return results

    def dismiss_in_ds(self, dossier: Dossier, user: Collegue, motivation: str):
        instructeur_id = self._get_instructeur_id(user)
        results = self.mutator.dossier_classer_sans_suite(
            dossier.ds_id, instructeur_id, motivation
        )
        self._check_results(results, dossier, user, "dismiss", value=motivation)
        return results

    # Annotations

    def update_ds_annotations_for_one_dotation(
        self,
        dossier: Dossier,
        user: Collegue,
        dotations_to_be_checked: list[POSSIBLE_DOTATIONS],
        annotations_dotation_to_update: POSSIBLE_DOTATIONS | None = None,
        assiette: float | None = None,
        montant: float | None = None,
        taux: float | None = None,
    ):
        if annotations_dotation_to_update is None:
            if assiette is not None or montant is not None or taux is not None:
                raise ValueError(
                    "annotations_dotation_to_update must be provided if assiette, montant or taux are provided"
                )

        annotations = [
            {
                "id": self._get_ds_field_id(dossier, "annotations_dotation"),
                "value": {"multipleDropDownList": dotations_to_be_checked},
            }
        ]

        if annotations_dotation_to_update:
            suffix = (
                "dsil" if annotations_dotation_to_update == DOTATION_DSIL else "detr"
            )

            if assiette is not None:
                annotations.append(
                    {
                        "id": self._get_ds_field_id(
                            dossier, f"annotations_assiette_{suffix}"
                        ),
                        "value": {"decimalNumber": assiette},
                    }
                )
            if montant is not None:
                annotations.append(
                    {
                        "id": self._get_ds_field_id(
                            dossier, f"annotations_montant_accorde_{suffix}"
                        ),
                        "value": {"decimalNumber": montant},
                    }
                )
            if taux is not None:
                annotations.append(
                    {
                        "id": self._get_ds_field_id(
                            dossier, f"annotations_taux_{suffix}"
                        ),
                        "value": {"decimalNumber": taux},
                    }
                )

        results = self.mutator.dossier_modifier_annotations(
            dossier.ds_id, user.ds_id, annotations
        )
        self._check_results(results, dossier, user, "annotations", value=annotations)
        self._update_updated_at_from_multiple_annotations(dossier, results)
        return results

    def update_checkboxes_annotations(
        self,
        dossier: Dossier,
        user: Collegue,
        annotations_to_update: dict[str, bool],
        text_annotations_to_update: dict[str, str],
    ):
        annotations = [
            {
                "id": self._get_ds_field_id(dossier, annotation_key),
                "value": {"checkbox": bool(annotation_value)},
            }
            for annotation_key, annotation_value in annotations_to_update.items()
        ]
        for annotation_key, annotation_value in text_annotations_to_update.items():
            annotations.append(
                {
                    "id": self._get_ds_field_id(dossier, annotation_key),
                    "value": {"text": annotation_value},
                }
            )
        results = self.mutator.dossier_modifier_annotations(
            dossier.ds_id, user.ds_id, annotations
        )
        self._check_results(results, dossier, user, "annotations", value=annotations)
        self._update_updated_at_from_multiple_annotations(dossier, results)
        return results

    # Private

    def _update_updated_at(self, dossier: Dossier, results: dict):
        updated_at = results.get("data", {}).get("updatedAt")
        if updated_at:
            dossier.ds_date_derniere_modification = updated_at
            dossier.save()

    def _update_updated_at_from_multiple_annotations(
        self, dossier: Dossier, results: dict
    ):
        most_recent_updated_at = None
        annotations = (
            results.get("data", {})
            .get("dossierModifierAnnotations", {})
            .get("annotations", [])
        )
        for annotation in annotations:
            updated_at = datetime.fromisoformat(annotation.get("updatedAt"))
            if updated_at and (
                most_recent_updated_at is None or updated_at > most_recent_updated_at
            ):
                most_recent_updated_at = updated_at

        if most_recent_updated_at:
            dossier.ds_date_derniere_modification = most_recent_updated_at
            dossier.save()

    def _get_instructeur_id(self, user: Collegue) -> str:
        instructeur_id = user.ds_id
        if bool(instructeur_id):
            return str(instructeur_id)

        raise InstructeurUnknown(extra={"user_id": user.id})

    def _get_ds_field_id(self, dossier: Dossier, field: str) -> str:
        try:
            ds_field = FieldMappingForComputer.objects.get(
                demarche=dossier.ds_data.ds_demarche_id, django_field=field
            )
            return ds_field.ds_field_id

        except FieldMappingForComputer.DoesNotExist:
            field_name = field
            try:
                field_name = Dossier._meta.get_field(field).verbose_name
            except FieldDoesNotExist:
                pass

            raise FieldError(
                f'Le champ "{field_name}" n\'existe pas dans la démarche {dossier.ds_demarche_number}.',
                extra={
                    "field_name": field_name,
                    "demarche_ds_number": dossier.ds_demarche_number,
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
                log_message="Error in DN mutation",
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
        if mutation_data is None or "errors" not in mutation_data:
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
            log_message="Error in DN mutation",
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
                    "Le dossier est en construction sur Démarche Numérique."
                )
            elif message == "An object of type Dossier was hidden due to permissions":
                new_messages.append("Vous n'avez pas accès à ce dossier.")
            else:
                new_messages.append(message)

        return ". ".join(new_messages)
