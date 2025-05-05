import pytest
from django import forms

from gsl_projet.constants import DOTATION_DETR
from gsl_projet.forms import DotationProjetForm
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import DotationProjetFactory


@pytest.fixture
def dotation_projet():
    return DotationProjetFactory(dotation=DOTATION_DETR, detr_avis_commission=None)


@pytest.mark.django_db
def test_dotation_projet_form_fields(dotation_projet):
    form = DotationProjetForm(instance=dotation_projet)

    expected_fields = [
        "detr_avis_commission",
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


@pytest.mark.django_db
def test_dotation_projet_form_validation(dotation_projet):
    valid_data = {
        "detr_avis_commission": True,
    }
    form = DotationProjetForm(instance=dotation_projet, data=valid_data)
    assert form.is_valid()

    invalid_data = {
        "detr_avis_commission": "invalid",
    }
    form = DotationProjetForm(instance=dotation_projet, data=invalid_data)
    assert not form.is_valid()
    assert "detr_avis_commission" in form.errors


@pytest.mark.django_db
def test_dotation_projet_form_save(dotation_projet):
    data = {
        "detr_avis_commission": True,
    }
    form = DotationProjetForm(instance=dotation_projet, data=data)
    assert form.is_valid()
    dotation_projet = form.save(commit=True)
    assert isinstance(dotation_projet, DotationProjet)
    assert dotation_projet.detr_avis_commission is True
