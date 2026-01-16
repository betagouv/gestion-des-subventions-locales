from unittest.mock import patch

import pytest
from django import forms

from gsl_core.tests.factories import CollegueWithDSProfileFactory
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.forms import ProjetForm
from gsl_projet.models import Projet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


@pytest.fixture
def projet():
    projet = ProjetFactory(
        is_in_qpv=False, is_attached_to_a_crte=False, is_budget_vert=False
    )
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    return projet


@pytest.fixture
def user():
    return CollegueWithDSProfileFactory()


@pytest.mark.django_db
def test_projet_form_fields(projet):
    form = ProjetForm(instance=projet)

    expected_fields = [
        "is_budget_vert",
        "is_in_qpv",
        "is_attached_to_a_crte",
        "is_frr",
        "is_acv",
        "is_pvd",
        "is_va",
        "is_autre_zonage_local",
        "is_contrat_local",
        "dotations",
    ]
    assert list(form.fields.keys()) == expected_fields

    budget_field = form.fields["is_budget_vert"]
    assert isinstance(budget_field, forms.BooleanField)
    assert budget_field.required is False
    assert (
        budget_field.label
        == "Projet concourant à la transition écologique au sens budget vert"
    )

    budget_field = form.fields["is_in_qpv"]
    assert isinstance(budget_field, forms.BooleanField)
    assert budget_field.required is False
    assert budget_field.label == "Projet situé en QPV"

    is_attached_to_a_crte = form.fields["is_attached_to_a_crte"]
    assert isinstance(is_attached_to_a_crte, forms.BooleanField)
    assert is_attached_to_a_crte.required is False

    dotations = form.fields["dotations"]
    assert isinstance(dotations, forms.MultipleChoiceField)
    assert dotations.required is False


@pytest.mark.django_db
def test_projet_form_validation(projet):
    valid_data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": False,
        "is_budget_vert": False,
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=valid_data)
    assert form.is_valid()

    invalid_data = {
        "is_in_qpv": "invalid",
        "is_attached_to_a_crte": "invalid",
        "is_budget_vert": "invalid",
        "dotations": [],
    }
    form = ProjetForm(instance=projet, data=invalid_data)
    assert not form.is_valid()
    assert "dotations" in form.errors

    # BooleanField cast string value to boolean
    assert "is_budget_vert" not in form.errors
    assert "is_in_qpv" not in form.errors
    assert "is_attached_to_a_crte" not in form.errors


@pytest.mark.django_db
def test_is_in_qpv_or_is_attached_to_a_crte_projet_form_validation(projet):
    invalid_data = {
        "is_in_qpv": "invalid value which will be transform to True",
        "is_attached_to_a_crte": "invalid value which will be transform to True",
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=invalid_data)
    assert form.is_valid()
    projet = form.save(commit=False)
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True


@pytest.mark.django_db
def test_projet_form_save(projet):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "is_budget_vert": False,
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_checkboxes_annotations"
    ):
        projet = form.save(commit=True)
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True
    assert projet.is_budget_vert is False
    assert projet.dotations == [DOTATION_DSIL]


@pytest.mark.django_db
def test_projet_form_save_with_multiple_dotations(projet):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "is_budget_vert": False,
        "dotations": [DOTATION_DSIL, DOTATION_DETR],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_checkboxes_annotations"
    ):
        projet = form.save(commit=True)

    assert DOTATION_DSIL in projet.dotations
    assert DOTATION_DETR in projet.dotations


@pytest.mark.django_db
def test_projet_form_save_with_field_exceptions(projet, user):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "is_budget_vert": True,
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data, user=user)
    assert form.is_valid()

    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_checkboxes_annotations"
    ) as mock_update_annotations:
        mock_update_annotations.side_effect = DsServiceException("Some error")
        try:
            projet = form.save(commit=True)
        except DsServiceException as e:
            assert str(e) == "Some error"

    projet.refresh_from_db()
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is False  # not updated
    assert projet.is_attached_to_a_crte is False  # not updated
    assert projet.is_budget_vert is False  # Default value
    assert projet.dotations == [DOTATION_DETR]  # Default value


@pytest.mark.django_db
def test_projet_form_cannot_change_dotations_when_notified(projet):
    """Test that dotations cannot be changed for a notified project"""
    from django.utils import timezone

    projet.notified_at = timezone.now()
    projet.save()

    # Try to change dotations from DETR to DSIL
    data = {
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert not form.is_valid()
    assert "dotations" in form.errors
    assert (
        "Les dotations d'un projet déjà notifié ne peuvent être modifiées."
        in form.errors["dotations"]
    )


@pytest.mark.django_db
def test_projet_form_allows_same_dotations_when_notified(projet):
    """Test that keeping the same dotations is allowed for a notified project"""
    from django.utils import timezone

    projet.notified_at = timezone.now()
    projet.save()

    # Keep the same dotations (DETR)
    data = {
        "dotations": [DOTATION_DETR],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
