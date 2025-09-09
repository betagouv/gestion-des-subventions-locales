import logging
from unittest import mock
from unittest.mock import patch

import pytest

from gsl_core.tests.factories import CollegueFactory
from gsl_demarches_simplifiees.models import Dossier, FieldMappingForComputer
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


def test_update_boolean_field_instructeur_unknown(dossier, caplog):
    caplog.set_level(logging.ERROR)
    user = CollegueFactory(ds_id="")
    service = DsService()

    with pytest.raises(InstructeurUnknown):
        service.update_ds_is_qpv(dossier, user, "true")
    assert "User does not have DS id." in caplog.text


@pytest.mark.parametrize(
    "field, field_name",
    (
        ("annotations_is_qpv", "Projet situé en QPV"),
        ("annotations_is_crte", "Projet rattaché à un CRTE"),
        (
            "annotations_is_budget_vert",
            "Projet concourant à la transition écologique au sens budget vert",
        ),
        ("field_unknown", "field_unknown"),
    ),
)
def test_update_update_boolean_field_field_error(
    user, dossier: Dossier, field, field_name, caplog
):
    caplog.set_level(logging.WARNING)
    ds_service = DsService()
    with patch(
        "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
        side_effect=FieldMappingForComputer.DoesNotExist,
    ):
        with pytest.raises(FieldError) as exc_info:
            ds_service._update_boolean_field(dossier, user, "true", field)

    assert (
        str(exc_info.value)
        == f'Le champs "{field_name}" n\'existe pas dans la démarche {dossier.ds_demarche.ds_number}.'
    )
    assert (
        f'Demarche #{dossier.ds_demarche_id} doesn\'t have field "{field}".'
        in caplog.text
    )


possible_responses = [
    # Instructeur has no rights
    (
        {
            "data": {
                "dossierModifierAnnotationCheckbox": {
                    "errors": [
                        {
                            "message": "L’instructeur n’a pas les droits d’accès à ce dossier"
                        }
                    ]
                }
            }
        },
        UserRightsError,
        "Vous n'avez pas les droits suffisants pour modifier ce champs.",
        logging.INFO,
        "Instructeur has no rights on the dossier",
    ),
    # Invalid payload (ex: wrong dossier id)
    (
        {
            "errors": [
                {
                    "message": "DossierModifierAnnotationCheckboxPayload not found",
                    "locations": [{"line": 2, "column": 3}],
                    "path": ["dossierModifierAnnotationCheckbox"],
                    "extensions": {"code": "not_found"},
                }
            ],
            "data": {"dossierModifierAnnotationCheckbox": None},
        },
        DsServiceException,
        "",
        logging.ERROR,
        "Error in DS boolean mutation",
    ),
    # Invalid field id
    (
        {
            "errors": [
                {
                    "message": 'Invalid input: "field_NUL"',
                    "locations": [{"line": 2, "column": 3}],
                    "path": ["dossierModifierAnnotationCheckbox"],
                }
            ],
            "data": {"dossierModifierAnnotationCheckbox": None},
        },
        DsServiceException,
        "",
        logging.ERROR,
        "Error in DS boolean mutation",
    ),
    # Invalid value
    (
        {
            "errors": [
                {
                    "message": 'Variable $input of type DossierModifierAnnotationCheckboxInput! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)',
                    "locations": [{"line": 1, "column": 37}],
                    "extensions": {
                        "value": {
                            "clientMutationId": "test",
                            "annotationId": "ZZZ",
                            "dossierId": "YYY",
                            "instructeurId": "XXX",
                            "value": "RIGOLO",
                        },
                        "problems": [
                            {
                                "path": ["value"],
                                "explanation": 'Could not coerce value "RIGOLO" to Boolean',
                            }
                        ],
                    },
                }
            ]
        },
        DsServiceException,
        "",
        logging.ERROR,
        "Error in DS boolean mutation",
    ),
    # Other error
    (
        {
            "data": {
                "dossierModifierAnnotationCheckbox": {
                    "errors": [{"message": "Une erreur"}]
                }
            }
        },
        DsServiceException,
        "Une erreur",
        logging.ERROR,
        "Error in DS boolean mutation",
    ),
]


@pytest.mark.parametrize(
    "mocked_response, exception, msg, log_level, log_msg", possible_responses
)
def test_update_boolean_field_error(
    user, dossier, ds_field, mocked_response, exception, msg, log_level, log_msg, caplog
):
    caplog.set_level(log_level)
    ds_service = DsService()
    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
            return_value=ds_field,
        ),
        patch.object(ds_service, "mutator") as mock_mutator,
    ):
        mock_mutator.dossier_modifier_annotation_checkbox.return_value = mocked_response
        with pytest.raises(exception) as exc_info:
            ds_service._update_boolean_field(
                dossier, user, "true", field="boolean_field"
            )

        assert str(exc_info.value) == msg
        assert log_msg in caplog.text
