from logging import getLogger

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.ds_client import DsMutator
from gsl_demarches_simplifiees.models import Dossier, FieldMappingForComputer

logger = getLogger(__name__)


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


# TODO peaufiner cette erreur. Elle peut venir d'un dossier non trouvé, d'un champs non trouvé ou d'un utilisateur qui n'a pas les droits
class UserRightsError(DsServiceException):
    DEFAULT_MESSAGE = "Vous n'avez pas les droits suffisants pour modifier ce champs."


class DsService:
    def __init__(self):
        self.mutator = DsMutator()

    def update_ds_is_qpv(
        self, dossier: Dossier, user: Collegue, value: str, field="annotations_is_qpv"
    ):
        instructeur_id = user.ds_id
        if not bool(instructeur_id):  # TODO test
            raise InstructeurUnknown

        try:
            ds_field = FieldMappingForComputer.objects.get(
                demarche=dossier.ds_demarche_id, django_field="annotations_is_qpv"
            )
        except FieldMappingForComputer.DoesNotExist:  # TODO test
            logger.warning(
                f'Demarche #{dossier.ds_demarche_id} doesn\'t have field "{field}".'
            )
            raise FieldError

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
            mutation_data = data[
                "dossierModifierAnnotationCheckbox"
            ]  # TODO make it dynamic
            if "errors" in mutation_data:
                errors = mutation_data["errors"]
                if bool(errors):
                    messages = [error["message"] for error in errors]
                    if (
                        "L’instructeur n’a pas les droits d’accès à ce dossier"
                        in messages
                    ):
                        raise UserRightsError

        return results
