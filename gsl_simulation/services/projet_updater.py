from django.db import transaction

from gsl_demarches_simplifiees.exceptions import (
    DsServiceException,
    InstructeurUnknown,
    UserRightsError,
)
from gsl_demarches_simplifiees.services import DsService

FIELDS_UPDATABLE_ON_DS = ["is_in_qpv", "is_attached_to_a_crte", "is_budget_vert"]


def process_projet_update(form, projet, user):
    """
    Returns a tuple(errors, has_blocking_error).
    - errors: field and errors mapping
    - has_blocking_error: True if global error (ex: UserRightsError)
    """
    errors = {}
    ds_service = DsService()

    with transaction.atomic():
        for field in FIELDS_UPDATABLE_ON_DS:
            if field in form.changed_data:
                try:
                    update_function = getattr(ds_service, f"update_ds_{field}")
                    update_function(
                        projet.dossier_ds,
                        user,
                        form.cleaned_data[field],
                    )
                except (UserRightsError, InstructeurUnknown) as e:
                    return {"all": e}, True  # global error -> stop
                except DsServiceException as e:
                    errors[field] = str(e)

        form.save(field_exceptions=errors.keys())

    return errors, False
