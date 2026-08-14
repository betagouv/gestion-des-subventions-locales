from unittest.mock import patch

import pytest

from gsl_core.tests.factories import CollegueWithDSProfileFactory
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.services import DsService
from gsl_historique.models import ProjetAction
from gsl_projet.forms import ProjetZonageForm
from gsl_projet.tests.factories import ProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def projet():
    return ProjetFactory(is_in_qpv=False, is_attached_to_a_crte=False)


@pytest.fixture
def user():
    return CollegueWithDSProfileFactory()


def test_autre_zonage_local_required_when_checkbox_checked(projet):
    form = ProjetZonageForm(
        instance=projet,
        data={"is_autre_zonage_local": True, "autre_zonage_local": ""},
    )
    assert not form.is_valid()
    assert (
        "Ce champ est obligatoire si le projet est rattaché à un autre zonage local."
        in form.errors["autre_zonage_local"]
    )


def test_autre_zonage_local_cleared_when_checkbox_unchecked(projet):
    projet.autre_zonage_local = "Zonage ABC"
    projet.save()
    form = ProjetZonageForm(
        instance=projet,
        data={"is_autre_zonage_local": False, "autre_zonage_local": "Zonage ABC"},
    )
    assert form.is_valid()
    assert form.save(commit=False).autre_zonage_local == ""


def test_contrat_local_required_when_checkbox_checked(projet):
    form = ProjetZonageForm(
        instance=projet,
        data={"is_contrat_local": True, "contrat_local": ""},
    )
    assert not form.is_valid()
    assert (
        "Ce champ est obligatoire si le projet est rattaché à un contrat local."
        in form.errors["contrat_local"]
    )


def test_contrat_local_cleared_when_checkbox_unchecked(projet):
    projet.contrat_local = "Contrat XYZ"
    projet.save()
    form = ProjetZonageForm(
        instance=projet,
        data={"is_contrat_local": False, "contrat_local": "Contrat XYZ"},
    )
    assert form.is_valid()
    assert form.save(commit=False).contrat_local == ""


@patch.object(DsService, "update_annotations")
def test_zonage_form_save_pushes_annotations_and_logs_history(
    mock_update_annotations, projet, user
):
    form = ProjetZonageForm(
        instance=projet,
        data={"is_in_qpv": "on", "is_attached_to_a_crte": "on"},
        user=user,
    )
    assert form.is_valid()
    form.save(commit=True)

    projet.refresh_from_db()
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True

    # Single dict, with the DN-specific keys for qpv/crte
    mock_update_annotations.assert_called_once()
    annotations = mock_update_annotations.call_args.kwargs["annotations"]
    assert annotations["annotations_is_qpv"] is True
    assert annotations["annotations_is_crte"] is True

    # Only the changed booleans are logged, under their field label
    logged = {
        action.boolean_field: action.boolean_value
        for action in ProjetAction.objects.filter(
            projet=projet, action_type=ProjetAction.TYPE_BOOLEAN_MODIFIED
        )
    }
    assert logged == {
        "Projet situé en QPV": True,
        "Projet rattaché à un CRTE": True,
    }


@patch.object(DsService, "update_annotations")
def test_zonage_form_save_pushes_text_annotations(
    mock_update_annotations, projet, user
):
    form = ProjetZonageForm(
        instance=projet,
        data={
            "is_autre_zonage_local": True,
            "autre_zonage_local": "Zonage ABC",
            "is_contrat_local": True,
            "contrat_local": "Contrat XYZ",
        },
        user=user,
    )
    assert form.is_valid()
    form.save(commit=True)

    projet.refresh_from_db()
    assert projet.autre_zonage_local == "Zonage ABC"
    assert projet.contrat_local == "Contrat XYZ"

    annotations = mock_update_annotations.call_args.kwargs["annotations"]
    assert annotations["annotations_is_autre_zonage_local"] is True
    assert annotations["annotations_autre_zonage_local"] == "Zonage ABC"
    assert annotations["annotations_contrat_local"] == "Contrat XYZ"


def test_zonage_form_save_rolls_back_on_dn_error(projet, user):
    form = ProjetZonageForm(
        instance=projet,
        data={"is_in_qpv": "on", "is_attached_to_a_crte": "on"},
        user=user,
    )
    assert form.is_valid()
    with patch.object(
        DsService,
        "update_annotations",
        side_effect=DsServiceException("Erreur DN"),
    ):
        form.save(commit=True)

    # The DN error is surfaced as a non-field error and the local writes roll back
    assert "Erreur DN" in str(form.non_field_errors())
    projet.refresh_from_db()
    assert projet.is_in_qpv is False
    assert projet.is_attached_to_a_crte is False
    assert not ProjetAction.objects.filter(projet=projet).exists()
