from unittest.mock import patch

import pytest

from gsl_core.tests.factories import CollegueFactory
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


def test_update_ds_is_qpv_success(user, dossier, ds_field):
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
        result = ds_service.update_ds_is_qpv(dossier, user, "true")
        assert "data" in result


def test_update_ds_is_qpv_instructeur_unknown(dossier):
    user = CollegueFactory(ds_id="")
    service = DsService()
    with pytest.raises(InstructeurUnknown):
        service.update_ds_is_qpv(dossier, user, "true")


def test_update_ds_is_qpv_field_error(user, dossier):
    ds_service = DsService()
    with patch(
        "gsl_demarches_simplifiees.services.FieldMappingForComputer.objects.get",
        side_effect=FieldError,
    ):
        with pytest.raises(FieldError):
            ds_service.update_ds_is_qpv(dossier, user, "true")


def test_update_ds_is_qpv_rights_error(user, dossier, ds_field):
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
            ds_service.update_ds_is_qpv(dossier, user, "true")


def test_update_ds_is_qpv_ds_service_exception(user, dossier, ds_field):
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
            ds_service.update_ds_is_qpv(dossier, user, "true")
