import pytest
from django import forms

from gsl_projet.constants import DOTATION_DETR
from gsl_projet.forms import DotationProjetForm
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import DotationProjetFactory


@pytest.fixture
def dotation_projet():
    return DotationProjetFactory(dotation=DOTATION_DETR)


@pytest.mark.django_db
def test_projet_form_fields(dotation_projet):
    form = DotationProjetForm(instance=dotation_projet)

    expected_fields = [
        "detr_avis_commission",
        "is_budget_vert",
        "is_in_qpv",
        "is_attached_to_a_crte",
    ]
    assert list(form.fields.keys()) == expected_fields

    avis_field = form.fields["detr_avis_commission"]
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
def test_projet_form_validation(dotation_projet):
    valid_data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": False,
        "detr_avis_commission": True,
        "is_budget_vert": False,
    }
    form = DotationProjetForm(instance=dotation_projet, data=valid_data)
    assert form.is_valid()

    invalid_data = {
        "is_in_qpv": "invalid",
        "is_attached_to_a_crte": "invalid",
        "detr_avis_commission": "invalid",
        "is_budget_vert": "invalid",
    }
    form = DotationProjetForm(instance=dotation_projet, data=invalid_data)
    assert not form.is_valid()
    assert "detr_avis_commission" in form.errors
    assert "is_budget_vert" in form.errors
    assert "is_in_qpv" not in form.errors
    assert "is_attached_to_a_crte" not in form.errors


@pytest.mark.django_db
def test_is_in_qpv_or_is_attached_to_a_crte_projet_form_validation(dotation_projet):
    invalid_data = {
        "is_in_qpv": "invalid value which will be transform to True",
        "is_attached_to_a_crte": "invalid value which will be transform to True",
    }
    form = DotationProjetForm(instance=dotation_projet, data=invalid_data)
    assert form.is_valid()
    dotation_projet = form.save(commit=False)
    assert isinstance(dotation_projet, DotationProjet)
    assert dotation_projet.projet.is_in_qpv is True
    assert dotation_projet.projet.is_attached_to_a_crte is True


@pytest.mark.django_db
def test_projet_form_save(dotation_projet):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "detr_avis_commission": True,
        "is_budget_vert": False,
    }
    form = DotationProjetForm(instance=dotation_projet, data=data)
    assert form.is_valid()
    dotation_projet = form.save(commit=True)
    assert isinstance(dotation_projet, DotationProjet)
    assert dotation_projet.detr_avis_commission is True
    assert dotation_projet.projet.is_in_qpv is True
    assert dotation_projet.projet.is_attached_to_a_crte is True
    assert dotation_projet.projet.is_budget_vert == "False"
