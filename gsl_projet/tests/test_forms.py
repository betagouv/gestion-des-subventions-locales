import pytest
from django import forms

from gsl_projet.forms import ProjetForm
from gsl_projet.models import Projet


@pytest.mark.django_db
def test_projet_form_fields():
    form = ProjetForm()

    expected_fields = [
        "is_in_qpv",
        "is_attached_to_a_crte",
        "avis_commission_detr",
        "is_budget_vert",
    ]
    assert list(form.fields.keys()) == expected_fields

    avis_field = form.fields["avis_commission_detr"]
    assert isinstance(avis_field, forms.ChoiceField)
    assert avis_field.required is False
    assert avis_field.choices == [
        (None, "En cours"),
        (True, "Oui"),
        (False, "Non"),
    ]
    assert avis_field.label == "Sélectionner l'avis de la commission d'élus DETR :"

    budget_field = form.fields["is_budget_vert"]
    assert isinstance(budget_field, forms.ChoiceField)
    assert budget_field.required is False
    assert budget_field.choices == [
        (None, "Non Renseigné"),
        (True, "Oui"),
        (False, "Non"),
    ]
    assert budget_field.label == "Transition écologique"


@pytest.mark.django_db
def test_projet_form_validation():
    valid_data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": False,
        "avis_commission_detr": True,
        "is_budget_vert": False,
    }
    form = ProjetForm(data=valid_data)
    assert form.is_valid()

    invalid_data = {
        "is_in_qpv": "invalid",
        "is_attached_to_a_crte": "invalid",
        "avis_commission_detr": "invalid",
        "is_budget_vert": "invalid",
    }
    form = ProjetForm(data=invalid_data)
    assert not form.is_valid()
    assert "avis_commission_detr" in form.errors
    assert "is_budget_vert" in form.errors
    assert "is_in_qpv" not in form.errors
    assert "is_attached_to_a_crte" not in form.errors


@pytest.mark.django_db
def test_is_in_qpv_or_is_attached_to_a_crte_projet_form_validation():
    invalid_data = {
        "is_in_qpv": "invalid value which will be transform to True",
        "is_attached_to_a_crte": "invalid value which will be transform to True",
    }
    form = ProjetForm(data=invalid_data)
    assert form.is_valid()
    projet = form.save(commit=False)
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True


@pytest.mark.django_db
def test_projet_form_save():
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "avis_commission_detr": True,
        "is_budget_vert": False,
    }
    form = ProjetForm(data=data)
    assert form.is_valid()
    projet = form.save(commit=False)
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True
    assert projet.avis_commission_detr is True
    assert projet.is_budget_vert is False
