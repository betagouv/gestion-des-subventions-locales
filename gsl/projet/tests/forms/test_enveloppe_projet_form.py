import pytest
from django import forms

from ...constants import DOTATION_DETR
from ...forms import EnveloppeProjetForm
from ...models import EnveloppeProjet
from ..factories import EnveloppeProjetFactory


@pytest.fixture
def enveloppe_projet():
    return EnveloppeProjetFactory(dotation=DOTATION_DETR, detr_avis_commission=None)


@pytest.mark.django_db
def test_enveloppe_projet_form_fields(enveloppe_projet):
    form = EnveloppeProjetForm(instance=enveloppe_projet)

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
    assert avis_field.label == "L'avis de la commission est-il positif ?"


@pytest.mark.django_db
def test_enveloppe_projet_form_validation(enveloppe_projet):
    valid_data = {
        "detr_avis_commission": True,
    }
    form = EnveloppeProjetForm(instance=enveloppe_projet, data=valid_data)
    assert form.is_valid()

    invalid_data = {
        "detr_avis_commission": "invalid",
    }
    form = EnveloppeProjetForm(instance=enveloppe_projet, data=invalid_data)
    assert not form.is_valid()
    assert "detr_avis_commission" in form.errors


@pytest.mark.django_db
def test_enveloppe_projet_form_save(enveloppe_projet):
    data = {
        "detr_avis_commission": True,
    }
    form = EnveloppeProjetForm(instance=enveloppe_projet, data=data)
    assert form.is_valid()
    enveloppe_projet = form.save(commit=True)
    assert isinstance(enveloppe_projet, EnveloppeProjet)
    assert enveloppe_projet.detr_avis_commission is True
