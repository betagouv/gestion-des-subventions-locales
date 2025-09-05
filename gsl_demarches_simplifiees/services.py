from logging import getLogger

from django.core.exceptions import FieldDoesNotExist

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.models import Dossier, FieldMappingForComputer

logger = getLogger(__name__)


# TODO peaufiner cette erreur ? Elle peut venir d'un dossier non trouvé, d'un champs non trouvé ou d'un instructeur non trouvé
class DsServiceException(Exception):
    DEFAULT_MESSAGE = "Erreur lors de la requête avec Démarches Simplifiées"

    def __init__(self, message=None, *args):
        if message is None:
            message = self.DEFAULT_MESSAGE
        super().__init__(message, *args)


class InstructeurUnknown(DsServiceException):
    DEFAULT_MESSAGE = "L'instructeur n'a pas d'id DS."


class FieldError(DsServiceException):
    DEFAULT_MESSAGE = "Le champs n'existe pas dans la démarche."


class UserRightsError(DsServiceException):
    DEFAULT_MESSAGE = "Vous n'avez pas les droits suffisants pour modifier ce champs."


class DsService:
    def __init__(self):
        self.mutator = DsMutator()

    def update_ds_is_qpv(self, dossier: Dossier, user: Collegue, value: str):
        return self._update_boolean_field(
            dossier, user, value, field="annotations_is_qpv"
        )

    def update_ds_is_budget_vert(self, dossier: Dossier, user: Collegue, value: str):
        return self._update_boolean_field(
            dossier, user, value, field="annotations_is_budget_vert"
        )

    def update_ds_is_crte(self, dossier: Dossier, user: Collegue, value: str):
        return self._update_boolean_field(
            dossier, user, value, field="annotations_is_crte"
        )

    def _update_boolean_field(
        self, dossier: Dossier, user: Collegue, value: str, field: str
    ):
        instructeur_id = user.ds_id
        if not bool(instructeur_id):
            raise InstructeurUnknown

        try:
            ds_field = FieldMappingForComputer.objects.get(
                demarche=dossier.ds_demarche_id, django_field=field
            )
        except FieldMappingForComputer.DoesNotExist:  # TODO test
            logger.warning(
                f'Demarche #{dossier.ds_demarche_id} doesn\'t have field "{field}".'
            )
            field_name = field
            try:
                field_name = Dossier._meta.get_field(field).verbose_name
            except FieldDoesNotExist:
                pass

            raise FieldError(
                f'Le champs "{field_name}" n\'existe pas dans la démarche.'
            )

        ds_field_id = ds_field.ds_field_id
        results = self.mutator.dossier_modifier_annotation_checkbox(
            dossier.ds_id, instructeur_id, ds_field_id, value
        )
        data = results.get("data", None)
        if data is None:
            if "errors" in results.keys():
                errors = results["errors"]
                messages = [error["message"] for error in errors]
                if "DossierModifierAnnotationCheckboxPayload not found" in messages:
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
                        raise UserRightsError
                    raise DsServiceException(
                        DsServiceException.DEFAULT_MESSAGE, *messages
                    )

        return results
