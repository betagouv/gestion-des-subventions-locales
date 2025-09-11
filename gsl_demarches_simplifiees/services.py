from logging import getLogger

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

logger = getLogger(__name__)


class DsService:
    def __init__(self):
        self.mutator = DsMutator()

    def update_ds_is_in_qpv(self, dossier: Dossier, user: Collegue, value: bool):
        return self._update_boolean_field(
            dossier, user, value, field="annotations_is_qpv"
        )

    def update_ds_is_budget_vert(
        self, dossier: Dossier, user: Collegue, value: bool | str
    ):
        return self._update_boolean_field(
            dossier, user, bool(value), field="annotations_is_budget_vert"
        )

    def update_ds_is_attached_to_a_crte(
        self, dossier: Dossier, user: Collegue, value: bool
    ):
        return self._update_boolean_field(
            dossier, user, value, field="annotations_is_crte"
        )

    def _update_boolean_field(
        self, dossier: Dossier, user: Collegue, value: bool, field: str
    ):
        instructeur_id = user.ds_id
        if not bool(instructeur_id):
            logger.error("User does not have DS id.", extra={"user_id": user.id})
            raise InstructeurUnknown

        try:
            ds_field = FieldMappingForComputer.objects.get(
                demarche=dossier.ds_demarche_id, django_field=field
            )
        except FieldMappingForComputer.DoesNotExist:
            logger.warning(
                f'Demarche #{dossier.ds_demarche_id} doesn\'t have field "{field}".'
            )
            field_name = field
            try:
                field_name = Dossier._meta.get_field(field).verbose_name
            except FieldDoesNotExist:
                pass

            raise FieldError(
                f'Le champ "{field_name}" n\'existe pas dans la démarche {dossier.ds_demarche.ds_number}.'
            )

        ds_field_id = ds_field.ds_field_id

        results = self.mutator.dossier_modifier_annotation_checkbox(
            dossier.ds_id, instructeur_id, ds_field_id, value
        )
        data = results.get("data", None)

        if (
            data is None
            or "dossierModifierAnnotationCheckbox" in data
            and data["dossierModifierAnnotationCheckbox"] is None
        ):
            if "errors" in results.keys():
                errors = results["errors"]
                messages = [error["message"] for error in errors]
                logger.error(
                    "Error in DS boolean mutation",
                    extra={
                        "dossier_id": dossier.id,
                        "user_id": user.id,
                        "field": field,
                        "value": value,
                        "error": messages,
                    },
                )
                raise DsServiceException

        else:
            mutation_data = data["dossierModifierAnnotationCheckbox"]
            if "errors" in mutation_data:
                errors = mutation_data["errors"]
                if bool(errors):
                    messages = [error["message"] for error in errors]
                    if (
                        "L’instructeur n’a pas les droits d’accès à ce dossier"
                        in messages
                    ):
                        logger.info(
                            "Instructeur has no rights on the dossier",
                            extra={
                                "dossier_id": dossier.id,
                                "user_id": user.id,
                            },
                        )
                        raise UserRightsError

                    logger.error(
                        "Error in DS boolean mutation",
                        extra={
                            "dossier_id": dossier.id,
                            "user_id": user.id,
                            "field": field,
                            "value": value,
                            "error": messages,
                        },
                    )
                    raise DsServiceException(*messages)

        return results
