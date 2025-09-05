from unittest import mock
from unittest.mock import patch

import pytest

from gsl_core.tests.factories import CollegueFactory
from gsl_demarches_simplifiees.models import FieldMappingForComputer
from gsl_demarches_simplifiees.services import (
    DsService,
    DsServiceException,
    FieldError,
    InstructeurUnknown,
    UserRightsError,
)
from gsl_demarches_simplifiees.tests.factories import (
    DossierFactory,
    FieldMappingForComputerFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return CollegueFactory(ds_id=123)


@pytest.fixture
def dossier():
    return DossierFactory(ds_id=456)


@pytest.fixture
def ds_field():
    return FieldMappingForComputerFactory(ds_field_id=101112)


@pytest.mark.parametrize(
    "function, field_name",
    (
        ("update_ds_is_qpv", "annotations_is_qpv"),
        ("update_ds_is_crte", "annotations_is_crte"),
        (
            "update_ds_is_budget_vert",
            "annotations_is_budget_vert",
        ),
    ),
)
@mock.patch.object(DsService, "_update_boolean_field")
def test_update_boolean_field_functions_call_generic_function_success(
    mocker, user, dossier, ds_field, function, field_name
):
    ds_service = DsService()

    ds_service_function = getattr(ds_service, function)
    ds_service_function(dossier, user, "true")
    mocker.assert_called_once_with(dossier, user, "true", field=field_name)


def test_update_boolean_field_success(user, dossier, ds_field):
    ds_service = DsService()
    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
            return_value=ds_field,
        ),
        patch.object(ds_service, "mutator") as mock_mutator,
    ):
        mock_mutator.dossier_modifier_annotation_checkbox.return_value = {
            "data": {
                "dossierModifierAnnotationCheckbox": {
                    "clientMutationId": "dev",
                    "annotation": {
                        "id": "Q2hhbXAtMzM3MDcwMg==",
                        "label": "Projet situé en QPV",
                        "stringValue": "true",
                    },
                    "errors": None,
                }
            }
        }
        result = ds_service._update_boolean_field(
            dossier, user, "true", field="boolean_field"
        )
        assert "data" in result


def test_update_boolean_field_instructeur_unknown(dossier):
    user = CollegueFactory(ds_id="")
    service = DsService()
    with pytest.raises(InstructeurUnknown):
        service.update_ds_is_qpv(dossier, user, "true")


@pytest.mark.parametrize(
    "function, field_name",
    (
        ("update_ds_is_qpv", "Projet situé en QPV"),
        ("update_ds_is_crte", "Projet rattaché à un CRTE"),
        (
            "update_ds_is_budget_vert",
            "Projet concourant à la transition écologique au sens budget vert",
        ),
    ),
)
def test_update_update_boolean_field_field_error(user, dossier, function, field_name):
    ds_service = DsService()
    with patch(
        "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
        side_effect=FieldMappingForComputer.DoesNotExist,
    ):
        with pytest.raises(FieldError) as exc_info:
            ds_service_function = getattr(ds_service, function)
            ds_service_function(dossier, user, "true")

    assert (
        str(exc_info.value)
        == f'Le champs "{field_name}" n\'existe pas dans la démarche.'
    )


def test_update_boolean_field_rights_error(user, dossier, ds_field):
    ds_service = DsService()
    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
            return_value=ds_field,
        ),
        patch.object(ds_service, "mutator") as mock_mutator,
    ):
        mock_mutator.dossier_modifier_annotation_checkbox.return_value = {
            "data": {
                "dossierModifierAnnotationCheckbox": {
                    "errors": [
                        {
                            "message": "L’instructeur n’a pas les droits d’accès à ce dossier"
                        }
                    ]
                }
            }
        }
        with pytest.raises(UserRightsError):
            ds_service._update_boolean_field(
                dossier, user, "true", field="boolean_field"
            )


def test_update_boolean_field_ds_service_exception(user, dossier, ds_field):
    ds_service = DsService()
    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
            return_value=ds_field,
        ),
        patch.object(ds_service, "mutator") as mock_mutator,
    ):
        mock_mutator.dossier_modifier_annotation_checkbox.return_value = {
            "errors": [
                {"message": "DossierModifierAnnotationCheckboxPayload not found"}
            ]
        }
        with pytest.raises(DsServiceException):
            ds_service._update_boolean_field(
                dossier, user, "true", field="boolean_field"
            )
