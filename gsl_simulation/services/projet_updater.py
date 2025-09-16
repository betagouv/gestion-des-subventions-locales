from typing import List, Literal, Mapping, get_args

from django.db import transaction

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
]
FIELDS_UPDATABLE_ON_DS: List[DsUpdatableFields] = list(get_args(DsUpdatableFields))
FIELDS_TO_DS_SERVICE_FUNCTIONS: Mapping[DsUpdatableFields, str] = {
    "is_in_qpv": "update_ds_is_in_qpv",
    "is_attached_to_a_crte": "update_ds_is_attached_to_a_crte",
    "is_budget_vert": "update_ds_is_budget_vert",
    "assiette": "update_ds_assiette",
}


def process_projet_update(
    form, dossier: Dossier, user: Collegue
) -> tuple[dict[str, str], bool]:
    """
    Returns a tuple(errors, has_blocking_error).
    - errors: field and errors mapping
    - has_blocking_error: True if global error (ex: UserRightsError)
    """
    errors: dict[str, str] = {}
    ds_service = DsService()

    with transaction.atomic():
        for field in FIELDS_UPDATABLE_ON_DS:
            if field in form.changed_data:
                try:
                    update_function = getattr(
                        ds_service, FIELDS_TO_DS_SERVICE_FUNCTIONS[field]
                    )
                    update_function(
                        dossier,
                        user,
                        form.cleaned_data[field],
                    )
                except (UserRightsError, InstructeurUnknown, DsConnectionError) as e:
                    return {"all": str(e)}, True  # global error -> stop
                except DsServiceException as e:
                    errors[field] = str(e)

    return errors, False
