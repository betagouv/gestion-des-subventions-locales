from logging import getLogger
from typing import List, Literal, Mapping, get_args

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.exceptions import (
    DsConnectionError,
    DsServiceException,
    InstructeurUnknown,
    UserRightsError,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService

DsUpdatableFields = Literal[
    "is_in_qpv",
    "is_attached_to_a_crte",
    "is_budget_vert",
    "assiette",
    "montant",
]
FIELDS_UPDATABLE_ON_DS: List[DsUpdatableFields] = list(get_args(DsUpdatableFields))
FIELDS_TO_DS_SERVICE_FUNCTIONS: Mapping[DsUpdatableFields, str] = {
    "is_in_qpv": "update_ds_is_in_qpv",
    "is_attached_to_a_crte": "update_ds_is_attached_to_a_crte",
    "is_budget_vert": "update_ds_is_budget_vert",
    "assiette": "update_ds_assiette",
    "montant": "update_ds_montant",
}
FIELD_TO_LABEL_MAP = {
    "is_in_qpv": "QPV",
    "is_attached_to_a_crte": "CRTE",
    "is_budget_vert": "Budget vert",
    "assiette": "Assiette",
    "montant": "Montant",
    "taux": "Taux",
}

logger = getLogger(__name__)


class DSUpdateMixin:
    """
    Mixin pour factoriser la logique de mise à jour DS dans les formulaires.
    Les sous-classes doivent définir :
      - get_dossier_ds(instance)
      - get_fields()
      - reset_field(field, instance)
      - post_save(instance)
    """

    def __init__(self, *args, **kwargs):
        self.user: Collegue | None = None
        if "user" in kwargs:
            self.user = kwargs.pop("user")
        return super().__init__(*args, **kwargs)

    def _save_with_ds(self, instance, commit=True):
        error_msg = None

        if commit:
            if self.user is None:
                logger.warning(
                    f"No user provided to {self.__class__.__name__}.save, can't save to DS"
                )
            else:
                errors, blocking = self.process_projet_update(instance)

                if blocking:
                    error_msg = (
                        "Une erreur est survenue lors de la mise à jour des informations "
                        f"sur Démarches Simplifiées. {errors['all']}"
                    )
                    return instance, error_msg

                for field in errors.keys():
                    self.reset_field(field, instance)

                if errors:
                    fields_msg = self.build_error_message(errors)
                    error_msg = (
                        "Une erreur est survenue lors de la mise à jour de certaines "
                        "informations sur Démarches Simplifiées "
                        f"({fields_msg}). Ces modifications n'ont pas été enregistrées."
                    )

            instance.save()
            self.post_save(instance)

        return instance, error_msg

    def build_error_message(self, errors):
        parts = []
        for field, msg in errors.items():
            label = FIELD_TO_LABEL_MAP.get(field, field)
            complete_message = f"{label} => {msg}" if msg else label
            parts.append(complete_message)
        return " / ".join(parts)

    def process_projet_update(
        self,
        instance,
    ) -> tuple[dict[str, str], bool]:
        """
        Returns a tuple(errors, has_blocking_error).
        - errors: field and errors mapping
        - has_blocking_error: True if global error (ex: UserRightsError)
        """
        errors: dict[str, str] = {}
        ds_service = DsService()
        dossier: Dossier = self.get_dossier_ds(instance)  # type: ignore

        for field in self.get_fields():
            if field in self.changed_data:  # type: ignore
                try:
                    update_function = getattr(
                        ds_service, FIELDS_TO_DS_SERVICE_FUNCTIONS[field]
                    )
                    update_function(
                        dossier,
                        self.user,
                        self.cleaned_data[field],  # type: ignore
                    )
                except (UserRightsError, InstructeurUnknown, DsConnectionError) as e:
                    return {"all": str(e)}, True  # global error -> stop
                except DsServiceException as e:
                    errors[field] = str(e)

        return errors, False

    def get_dossier_ds(self, instance):
        raise NotImplementedError

    def get_fields(self):
        raise NotImplementedError

    def reset_field(self, field, instance):
        raise NotImplementedError

    def post_save(self, instance):
        raise NotImplementedError
