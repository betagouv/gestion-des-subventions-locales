import pytest
from django import forms

from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.forms import ProjetForm
from gsl_projet.models import Projet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory


@pytest.fixture
def projet():
    projet = ProjetFactory(is_budget_vert=None)
    DotationProjetFactory(projet=projet, dotation=DOTATION_DETR)
    return projet


@pytest.mark.django_db
def test_projet_form_fields(projet):
    form = ProjetForm(instance=projet)

    expected_fields = [
        "is_budget_vert",
        "is_in_qpv",
        "is_attached_to_a_crte",
        "dotations",
    ]
    assert list(form.fields.keys()) == expected_fields

    budget_field = form.fields["is_budget_vert"]
    assert isinstance(budget_field, forms.ChoiceField)
    assert budget_field.required is False
    assert budget_field.choices == [
        (None, "Non Renseigné"),
        (True, "Oui"),
        (False, "Non"),
    ]
    assert budget_field.label == "Transition écologique"

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
    assert "is_budget_vert" in form.errors
    assert "dotations" in form.errors

    # BooleanField cast string value to boolean
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
    projet = form.save(commit=True)
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True
    assert projet.is_budget_vert is False
    assert projet.dotations == [DOTATION_DSIL]


@pytest.mark.django_db
def test_projet_form_save_with_field_exceptions(projet):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "is_budget_vert": False,
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    projet = form.save(commit=True, field_exceptions=["is_budget_vert"])
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True
    assert projet.is_budget_vert is None  # Default value
    assert projet.dotations == [DOTATION_DSIL]
