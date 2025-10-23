import copy
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
    ProfileFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return CollegueFactory(ds_profile=ProfileFactory())


@pytest.fixture
def dossier():
    return DossierFactory(ds_id=456)


@pytest.fixture
def ds_field():
    return FieldMappingForComputerFactory(ds_field_id=101112)


@pytest.mark.parametrize(
    "function, field_name",
    (
        ("update_ds_is_in_qpv", "annotations_is_qpv"),
        ("update_ds_is_attached_to_a_crte", "annotations_is_crte"),
    ),
)
@mock.patch.object(DsService, "_update_boolean_field")
def test_update_boolean_field_functions_call_generic_function_success(
    update_boolean_field_mocker, user, dossier, function, field_name
):
    ds_service = DsService()

    ds_service_function = getattr(ds_service, function)
    ds_service_function(dossier, user, "true")
    update_boolean_field_mocker.assert_called_once_with(
        dossier, user, "true", field_name
    )


@pytest.mark.parametrize(
    "value, expected_param", ((True, True), (False, False), ("", False))
)
@mock.patch.object(DsService, "_update_boolean_field")
def test_update_ds_is_budget_vert_functions_call_generic_function_success(
    update_boolean_field_mocker, user, dossier, value, expected_param
):
    ds_service = DsService()

    ds_service.update_ds_is_budget_vert(dossier, user, value)
    update_boolean_field_mocker.assert_called_once_with(
        dossier, user, expected_param, "annotations_is_budget_vert"
    )


@pytest.mark.parametrize(
    "function, field_name",
    (
        ("update_ds_assiette", "annotations_assiette"),
        ("update_ds_montant", "annotations_montant_accorde"),
        ("update_ds_taux", "annotations_taux"),
    ),
)
@mock.patch.object(DsService, "_update_decimal_field")
def test_update_decimal_field_functions_call_generic_function_success(
    update_boolean_field_mocker, user, dossier, function, field_name
):
    ds_service = DsService()

    ds_service_function = getattr(ds_service, function)
    ds_service_function(dossier, user, 250.33)
    update_boolean_field_mocker.assert_called_once_with(
        dossier, user, 250.33, field_name
    )


@mock.patch.object(DsService, "_update_decimal_field")
def test_update_decimal_field_functions_with_None(
    update_boolean_field_mocker, user, dossier
):
    ds_service = DsService()
    ds_service_function = getattr(ds_service, "update_ds_assiette")

    ds_service_function(dossier, user, None)
    update_boolean_field_mocker.assert_called_once_with(
        dossier, user, 0, "annotations_assiette"
    )


@pytest.mark.parametrize(
    "function, mutation_type",
    (("_update_boolean_field", "checkbox"), ("_update_decimal_field", "decimal")),
)
@mock.patch.object(DsService, "_update_annotation_field")
def test_update_annotation_field_is_called_by_mutation_type_functions(
    update_annotation_field_mocker, user, dossier, function, mutation_type
):
    ds_service = DsService()
    if mutation_type == "checkbox":
        value = True
    else:
        value = 1.5

    ds_service_function = getattr(ds_service, function)
    ds_service_function(dossier, user, value, "field")
    update_annotation_field_mocker.assert_called_once_with(
        dossier, user, value, "field", mutation_type
    )


@pytest.mark.parametrize(
    "function, mutation_type",
    (
        ("dossier_modifier_annotation_checkbox", "checkbox"),
        ("dossier_modifier_annotation_decimal", "decimal"),
    ),
)
def test_update_annotation_field_success(
    user, dossier, ds_field, function, mutation_type
):
    ds_service = DsService()

    value = True if mutation_type == "checkbox" else 1.5
    mutation_data_name = DsService.MUTATION_KEYS[mutation_type]

    with (
        patch(
            "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
            return_value=ds_field,
        ),
        patch.object(ds_service, "mutator") as mock_mutator,
    ):
        mock_function = getattr(mock_mutator, function)
        mock_function.return_value = {
            "data": {
                mutation_data_name: {
                    "clientMutationId": "dev",
                    "errors": None,
                }
            }
        }

        result = ds_service._update_annotation_field(
            dossier, user, value, "field", mutation_type
        )
        assert "data" in result


def test_get_instructeur_id(caplog):
    caplog.set_level(logging.ERROR)
    user = CollegueFactory()
    service = DsService()

    with pytest.raises(InstructeurUnknown):
        service._get_instructeur_id(user)
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
        (
            "annotations_assiette",
            "Montant des dépenses éligibles retenues (€)",
        ),
        (
            "annotations_montant_accorde",
            "Montant définitif de la subvention (€)",
        ),
        (
            "annotations_taux",
            "Taux de subvention (%)",
        ),
        ("field_unknown", "field_unknown"),
    ),
)
def test_get_ds_field_id(dossier: Dossier, field, field_name, caplog):
    caplog.set_level(logging.WARNING)
    ds_service = DsService()

    with patch(
        "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
        side_effect=FieldMappingForComputer.DoesNotExist,
    ):
        with pytest.raises(FieldError) as exc_info:
            ds_service._get_ds_field_id(dossier, field)

    assert (
        str(exc_info.value)
        == f'Le champ "{field_name}" n\'existe pas dans la démarche {dossier.ds_demarche.ds_number}.'
    )
    assert (
        f'Demarche #{dossier.ds_demarche_id} doesn\'t have field "{field}".'
        in caplog.text
    )


@pytest.mark.parametrize(
    "mutation_type",
    ("checkbox", "decimal", "dismiss"),
)
def test_check_results_with_uncorrect_user_rights(dossier, user, mutation_type, caplog):
    caplog.set_level(logging.INFO)
    ds_service = DsService()
    mutation_data_name = DsService.MUTATION_KEYS[mutation_type]
    response = {
        "data": {
            mutation_data_name: {
                "errors": [
                    {"message": "L’instructeur n’a pas les droits d’accès à ce dossier"}
                ]
            }
        }
    }

    with pytest.raises(UserRightsError) as exc_info:
        ds_service._check_results(
            response,
            dossier,
            user,
            mutation_type,
        )

    assert (
        str(exc_info.value)
        == "Vous n'avez pas les droits suffisants pour modifier ce dossier."
    )
    assert "Instructeur has no rights on the dossier" in caplog.text


possible_responses = [
    # Invalid payload (ex: wrong dossier id)
    (
        {
            "errors": [{"message": "__MUTATION_KEY__Payload not found"}],
            "data": {"__MUTATION_KEY__": None},
        },
        DsServiceException,
        "__MUTATION_KEY__Payload not found",
        "Error in DS mutation",
    ),
    # Invalid field id
    (
        {
            "errors": [{"message": 'Invalid input: "field_NUL"'}],
            "data": {"__MUTATION_KEY__": None},
        },
        DsServiceException,
        'Invalid input: "field_NUL"',
        "Error in DS mutation",
    ),
    # Invalid value
    (
        {
            "errors": [
                {
                    "message": 'Variable $input of type __MUTATION_KEY__Input! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)'
                }
            ]
        },
        DsServiceException,
        'Variable $input of type __MUTATION_KEY__Input! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)',
        "Error in DS mutation",
    ),
    # Other error
    (
        {"data": {"__MUTATION_KEY__": {"errors": [{"message": "Une erreur"}]}}},
        DsServiceException,
        "Une erreur",
        "Error in DS mutation",
    ),
]


@pytest.mark.parametrize("mutation_type", ("checkbox", "decimal", "dismiss"))
@pytest.mark.parametrize("mocked_response, exception, msg, log_msg", possible_responses)
def test_check_results(
    user,
    dossier,
    mutation_type,
    mocked_response,
    exception,
    msg,
    log_msg,
    caplog,
):
    caplog.set_level(logging.ERROR)
    ds_service = DsService()

    value = True if mutation_type == "checkbox" else 1.5
    mutation_data_name = DsService.MUTATION_KEYS[mutation_type]

    # clone + replace __MUTATION_KEY__ dynamically
    response = copy.deepcopy(mocked_response)
    response_str = str(response).replace("__MUTATION_KEY__", mutation_data_name)
    response = eval(response_str)  # safe because we control data

    with pytest.raises(exception) as exc_info:
        ds_service._check_results(
            response,
            dossier,
            user,
            mutation_type,
            value,
        )

    final_msg = msg.replace("__MUTATION_KEY__", mutation_data_name)
    assert str(exc_info.value) == final_msg
    assert log_msg in caplog.text


def test_dismiss_in_ds():
    dossier = DossierFactory()
    user = CollegueFactory()
    ds_service = DsService()
    with (
        patch(
            "gsl_demarches_simplifiees.services.DsService._get_instructeur_id"
        ) as mock_get_instructeur_id,
        patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_classer_sans_suite"
        ) as mock_dossier_classer_sans_suite,
        patch(
            "gsl_demarches_simplifiees.services.DsService._check_results"
        ) as mock_check_results,
    ):
        mock_get_instructeur_id.return_value = "instructeur_id"
        results = {"results": {"data": {}}}
        mock_dossier_classer_sans_suite.return_value = results

        ds_service.dismiss_in_ds(dossier, user, motivation="motivation")

        mock_get_instructeur_id.assert_called_once_with(user)
        mock_dossier_classer_sans_suite.assert_called_once_with(
            dossier.ds_id, "instructeur_id", "motivation"
        )
        mock_check_results.assert_called_once_with(
            results, dossier, user, "dismiss", value="motivation"
        )
