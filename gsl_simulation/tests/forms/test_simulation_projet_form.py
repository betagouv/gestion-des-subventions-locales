import pytest
from django import forms

from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.forms import SimulationProjetForm
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def simulation_projet():
    dotation_projet = DotationProjetFactory(assiette=1_000)
    return SimulationProjetFactory(
        dotation_projet=dotation_projet, montant=200, taux=20
    )


def test_montant_field(simulation_projet):
    form = SimulationProjetForm(instance=simulation_projet)
    assert "montant" in form.fields
    assert isinstance(form.fields["montant"], forms.DecimalField)
    assert form.fields["montant"].label == "Montant prévisionnel accordé (€)"
    assert form.fields["montant"].max_digits == 14
    assert form.fields["montant"].decimal_places == 2
    assert form.fields["montant"].required is False
    assert form.fields["montant"].widget.attrs["min"] == 0

    form = SimulationProjetForm(instance=simulation_projet, data={"montant": -1})
    assert not form.is_valid()


def test_taux_field(simulation_projet):
    form = SimulationProjetForm(instance=simulation_projet)
    assert "taux" in form.fields
    assert isinstance(form.fields["taux"], forms.DecimalField)
    assert form.fields["taux"].label == "Taux de subvention (%)"
    assert form.fields["taux"].max_digits == 5
    assert form.fields["taux"].decimal_places == 2
    assert form.fields["taux"].required is False
    assert form.fields["taux"].widget.attrs["min"] == 0
    assert form.fields["taux"].widget.attrs["max"] == 100

    form = SimulationProjetForm(instance=simulation_projet, data={"taux": -1})
    assert not form.is_valid()


def test_new_montant(simulation_projet):
    data = {
        "montant": 300,
        "taux": 20,
    }
    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["montant"] == 300
    assert form.cleaned_data["taux"] == 30
    form.save()
    assert simulation_projet.montant == 300
    assert simulation_projet.taux == 30


def test_new_taux(simulation_projet):
    data = {
        "montant": 200,
        "taux": 30,
    }
    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["montant"] == 300  # calculated from taux
    assert form.cleaned_data["taux"] == 30
    form.save()
    assert simulation_projet.montant == 300
    assert simulation_projet.taux == 30


def test_coherent_both_new_montant_and_new_taux(simulation_projet):
    data = {
        "montant": 300,
        "taux": 30,
    }
    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["montant"] == 300
    assert form.cleaned_data["taux"] == 30
    form.save()
    assert simulation_projet.montant == 300
    assert simulation_projet.taux == 30


def test_incoherent_both_new_montant_and_new_taux(simulation_projet):
    data = {
        "montant": 400,
        "taux": 30,
    }
    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert not form.is_valid()
    assert "montant" in form.errors
    assert "taux" in form.errors
    assert form.errors["montant"] == ["Le montant doit être cohérent avec le taux."]
    assert form.errors["taux"] == ["Le taux doit être cohérent avec le montant."]
