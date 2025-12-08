import copy
import logging
from unittest import mock
from unittest.mock import patch

import pytest
from django.utils import timezone

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
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL

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
@pytest.mark.parametrize(
    "dotation",
    (DOTATION_DSIL, DOTATION_DETR),
)
@mock.patch.object(DsService, "_update_decimal_field")
def test_update_decimal_field_functions_call_generic_function_success(
    update_decimal_field_mocker, user, dossier, function, field_name, dotation
):
    ds_service = DsService()

    suffix = "dsil" if dotation == DOTATION_DSIL else "detr"
    field_complete_name = f"{field_name}_{suffix}"

    ds_service_function = getattr(ds_service, function)
    ds_service_function(dossier, user, dotation, 250.33)
    update_decimal_field_mocker.assert_called_once_with(
        dossier, user, 250.33, field_complete_name
    )


@mock.patch.object(DsService, "_update_decimal_field")
def test_update_decimal_field_functions_with_None(
    update_boolean_field_mocker, user, dossier
):
    ds_service = DsService()
    ds_service_function = getattr(ds_service, "update_ds_assiette")

    ds_service_function(dossier, user, DOTATION_DSIL, None)
    update_boolean_field_mocker.assert_called_once_with(
        dossier, user, 0, "annotations_assiette_dsil"
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


@pytest.mark.parametrize(
    "function, mutation_type",
    (
        ("dossier_modifier_annotation_checkbox", "checkbox"),
        ("dossier_modifier_annotation_decimal", "decimal"),
    ),
)
def test_update_annotation_field_updates_ds_date_derniere_modification(
    user, dossier, ds_field, function, mutation_type
):
    ds_service = DsService()

    value = True if mutation_type == "checkbox" else 1.5
    mutation_data_name = DsService.MUTATION_KEYS[mutation_type]
    updated_at_iso = "2025-01-15T10:30:00+00:00"
    expected_updated_at = timezone.datetime.fromisoformat(updated_at_iso)

    dossier.ds_date_derniere_modification = None
    dossier.save()

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
                },
                "updatedAt": updated_at_iso,
            }
        }

        ds_service._update_annotation_field(
            dossier, user, value, "field", mutation_type
        )

        dossier.refresh_from_db()
        assert dossier.ds_date_derniere_modification == expected_updated_at


def test_get_instructeur_id(caplog):
    caplog.set_level(logging.WARNING)
    user = CollegueFactory()
    service = DsService()

    with pytest.raises(InstructeurUnknown):
        service._get_instructeur_id(user)
    assert "User does not have DS id" in caplog.text


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
    caplog.set_level(logging.ERROR)
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
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "Field not found in demarche"
    assert getattr(record, "field_name") == field_name
    assert getattr(record, "demarche_ds_number") == dossier.ds_demarche.ds_number
    assert getattr(record, "dossier_ds_number") == dossier.ds_number


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
        "__MUTATION_KEY__Payload not found",
    ),
    # Invalid field id
    (
        {
            "errors": [{"message": 'Invalid input: "field_NUL"'}],
            "data": {"__MUTATION_KEY__": None},
        },
        'Invalid input: "field_NUL"',
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
        'Variable $input of type __MUTATION_KEY__Input! was provided invalid value for value (Could not coerce value "RIGOLO" to Boolean)',
    ),
    # Other error
    (
        {"data": {"__MUTATION_KEY__": {"errors": [{"message": "Une erreur"}]}}},
        "Une erreur",
    ),
]


@pytest.mark.parametrize("mutation_type", ("checkbox", "decimal", "dismiss"))
@pytest.mark.parametrize("mocked_response, msg", possible_responses)
def test_check_results(
    user,
    dossier,
    mutation_type,
    mocked_response,
    msg,
    caplog,
):
    caplog.set_level(logging.WARNING)
    ds_service = DsService()

    value = True if mutation_type == "checkbox" else 1.5
    mutation_data_name = DsService.MUTATION_KEYS[mutation_type]

    # clone + replace __MUTATION_KEY__ dynamically
    response = copy.deepcopy(mocked_response)
    response_str = str(response).replace("__MUTATION_KEY__", mutation_data_name)
    response = eval(response_str)  # safe because we control data

    with pytest.raises(DsServiceException) as exc_info:
        ds_service._check_results(
            response,
            dossier,
            user,
            mutation_type,
            value,
        )

    final_msg = msg.replace("__MUTATION_KEY__", mutation_data_name)
    assert str(exc_info.value) == final_msg
    assert "Error in DS mutation" in caplog.text


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


def test_update_ds_annotations_for_one_dotation_annotations_dict(user, dossier):
    """Test that update_ds_annotations_for_one_dotation builds annotations dict correctly"""
    ds_service = DsService()

    # Mock field IDs
    field_ids = {
        "annotations_dotation": "field_dotations_123",
        "annotations_assiette_dsil": "field_assiette_dsil_456",
        "annotations_assiette_detr": "field_assiette_detr_789",
        "annotations_montant_accorde_dsil": "field_montant_dsil_101",
        "annotations_montant_accorde_detr": "field_montant_detr_102",
        "annotations_taux_dsil": "field_taux_dsil_103",
        "annotations_taux_detr": "field_taux_detr_104",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results") as mock_check_results,
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        # Test with DSIL, all parameters provided
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            annotations_dotation_to_update=DOTATION_DSIL,
            dotations_to_be_checked=[DOTATION_DSIL, DOTATION_DETR],
            assiette=1000.50,
            montant=500.25,
            taux=50.0,
        )

        # Verify annotations dict was built correctly
        call_args = mock_mutator.dossier_modifier_annotations.call_args
        annotations = call_args[0][2]  # Third argument is annotations

        assert len(annotations) == 4  # dotations + assiette + montant + taux

        # Check dotations annotation (always first)
        assert annotations[0] == {
            "id": "field_dotations_123",
            "value": {"multipleDropDownList": [DOTATION_DSIL, DOTATION_DETR]},
        }

        # Check assiette annotation
        assert annotations[1] == {
            "id": "field_assiette_dsil_456",
            "value": {"decimalNumber": 1000.50},
        }

        # Check montant annotation
        assert annotations[2] == {
            "id": "field_montant_dsil_101",
            "value": {"decimalNumber": 500.25},
        }

        # Check taux annotation
        assert annotations[3] == {
            "id": "field_taux_dsil_103",
            "value": {"decimalNumber": 50.0},
        }

        # Verify _check_results was called with annotations
        mock_check_results.assert_called_once()
        check_call_args = mock_check_results.call_args[0]
        assert check_call_args[3] == "annotations"  # mutation_type
        assert check_call_args[4] == annotations  # value (annotations list)


@pytest.mark.parametrize(
    "dotation, expected_suffix",
    [(DOTATION_DSIL, "dsil"), (DOTATION_DETR, "detr")],
)
def test_update_ds_annotations_for_one_dotation_suffix(
    user, dossier, dotation, expected_suffix
):
    """Test that correct suffix is used based on dotation type"""
    ds_service = DsService()

    field_ids = {
        "annotations_dotation": "field_dotations_123",
        f"annotations_assiette_{expected_suffix}": f"field_assiette_{expected_suffix}_456",
        f"annotations_montant_accorde_{expected_suffix}": f"field_montant_{expected_suffix}_101",
        f"annotations_taux_{expected_suffix}": f"field_taux_{expected_suffix}_103",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results"),
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            annotations_dotation_to_update=dotation,
            dotations_to_be_checked=[dotation],
            assiette=1000.0,
            montant=500.0,
            taux=50.0,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]

        # Verify suffix is used in field IDs
        assert annotations[1]["id"] == f"field_assiette_{expected_suffix}_456"
        assert annotations[2]["id"] == f"field_montant_{expected_suffix}_101"
        assert annotations[3]["id"] == f"field_taux_{expected_suffix}_103"


@pytest.mark.parametrize(
    "assiette, montant, taux, expected_count",
    [
        (None, None, None, 1),  # Only dotations
        (1000.0, None, None, 2),  # dotations + assiette
        (None, 500.0, None, 2),  # dotations + montant
        (None, None, 50.0, 2),  # dotations + taux
        (1000.0, 500.0, None, 3),  # dotations + assiette + montant
        (1000.0, None, 50.0, 3),  # dotations + assiette + taux
        (None, 500.0, 50.0, 3),  # dotations + montant + taux
        (1000.0, 500.0, 50.0, 4),  # All parameters
    ],
)
def test_update_ds_annotations_for_one_dotation_optional_params(
    user, dossier, assiette, montant, taux, expected_count
):
    """Test that optional parameters (assiette, montant, taux) are only included when not None"""
    ds_service = DsService()

    field_ids = {
        "annotations_dotation": "field_dotations_123",
        "annotations_assiette_detr": "field_assiette_detr_456",
        "annotations_montant_accorde_detr": "field_montant_detr_101",
        "annotations_taux_detr": "field_taux_detr_103",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results"),
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            annotations_dotation_to_update=DOTATION_DETR,
            dotations_to_be_checked=[DOTATION_DETR],
            assiette=assiette,
            montant=montant,
            taux=taux,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]

        # Verify correct number of annotations
        assert len(annotations) == expected_count

        # First annotation should always be dotations
        assert annotations[0]["id"] == "field_dotations_123"
        assert "multipleDropDownList" in annotations[0]["value"]

        # Verify only non-None parameters are included
        annotation_ids = [ann["id"] for ann in annotations[1:]]
        if assiette is not None:
            assert "field_assiette_detr_456" in annotation_ids
        if montant is not None:
            assert "field_montant_detr_101" in annotation_ids
        if taux is not None:
            assert "field_taux_detr_103" in annotation_ids


def test_update_ds_annotations_for_one_dotation_dotations_list(user, dossier):
    """Test that dotations_to_be_checked is correctly passed as multipleDropDownList"""
    ds_service = DsService()

    field_ids = {
        "annotations_dotation": "field_dotations_123",
    }

    def mock_get_ds_field_id(dossier, field):
        return field_ids[field]

    with (
        patch.object(ds_service, "_get_ds_field_id", side_effect=mock_get_ds_field_id),
        patch.object(ds_service, "mutator") as mock_mutator,
        patch.object(ds_service, "_check_results"),
    ):
        mock_mutator.dossier_modifier_annotations.return_value = {
            "data": {"dossierModifierAnnotations": {"clientMutationId": "test"}}
        }

        dotations_list = [DOTATION_DSIL]
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            annotations_dotation_to_update=DOTATION_DSIL,
            dotations_to_be_checked=dotations_list,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]

        # Verify dotations list is correctly formatted
        assert annotations[0]["value"]["multipleDropDownList"] == dotations_list

        # Test with multiple dotations
        dotations_list = [DOTATION_DSIL, DOTATION_DETR]
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=dossier,
            user=user,
            annotations_dotation_to_update=DOTATION_DSIL,
            dotations_to_be_checked=dotations_list,
        )

        annotations = mock_mutator.dossier_modifier_annotations.call_args[0][2]
        assert annotations[0]["value"]["multipleDropDownList"] == dotations_list


class TestTransformMessage:
    def test_transform_message_known_phrases(self):
        ds = DsService()
        messages = ["Le dossier est déjà en\xa0construction"]
        out = ds._transform_message(messages)
        assert "Le dossier est en construction sur Démarches Simplifiées." in out

    def test_transform_message_permission_phrase(self):
        ds = DsService()
        messages = ["An object of type Dossier was hidden due to permissions"]
        out = ds._transform_message(messages)
        assert "Vous n'avez pas accès à ce dossier." in out

    def test_transform_message_generic(self):
        ds = DsService()
        messages = ["Une erreur"]
        out = ds._transform_message(messages)
        assert out == "Une erreur"
