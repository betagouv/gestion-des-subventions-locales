import pytest
from django import forms

from gsl_projet.tests.factories import DetrProjetFactory
from gsl_simulation.forms import SimulationProjetForm
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def simulation_projet():
    dotation_projet = DetrProjetFactory(assiette=1_000)
    return SimulationProjetFactory(dotation_projet=dotation_projet, montant=200)


@pytest.fixture
def initial_data():
    return {
        "assiette": 1_000,
        "montant": 200,
        "taux": 20,
    }


def test_assiette_field(simulation_projet):
    form = SimulationProjetForm(instance=simulation_projet)
    assert "assiette" in form.fields
    assert isinstance(form.fields["assiette"], forms.DecimalField)
    assert (
        form.fields["assiette"].label == "Montant des dépenses éligibles retenues (€)"
    )
    assert form.fields["assiette"].max_digits == 12
    assert form.fields["assiette"].decimal_places == 2
    assert form.fields["assiette"].required is False
    assert form.fields["assiette"].widget.attrs["min"] == 0

    form = SimulationProjetForm(instance=simulation_projet, data={"montant": -1})
    assert not form.is_valid()


def test_montant_field(simulation_projet):
    form = SimulationProjetForm(instance=simulation_projet)
    assert "montant" in form.fields
    assert isinstance(form.fields["montant"], forms.DecimalField)
    assert form.fields["montant"].label == "Montant prévisionnel accordé (€)"
    assert form.fields["montant"].max_digits == 12
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
    assert form.fields["taux"].max_digits == 6
    assert form.fields["taux"].decimal_places == 3
    assert form.fields["taux"].required is False
    assert form.fields["taux"].widget.attrs["min"] == 0
    assert form.fields["taux"].widget.attrs["max"] == 100

    form = SimulationProjetForm(instance=simulation_projet, data={"taux": -1})
    assert not form.is_valid()


def test_new_montant(simulation_projet, initial_data):
    data = initial_data
    data["montant"] = 300

    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["montant"] == 300
    assert form.cleaned_data["taux"] == 30
    form.save()
    assert simulation_projet.montant == 300
    assert simulation_projet.taux == 30


def test_new_taux(simulation_projet, initial_data):
    data = initial_data
    data["taux"] = 30

    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["montant"] == 300  # calculated from taux
    assert form.cleaned_data["taux"] == 30
    form.save()
    assert simulation_projet.montant == 300
    assert simulation_projet.taux == 30


def test_coherent_new_montant_and_new_taux(simulation_projet, initial_data):
    data = initial_data
    data["montant"] = 300
    data["taux"] = 30

    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["montant"] == 300
    assert form.cleaned_data["taux"] == 30
    form.save()
    assert simulation_projet.montant == 300
    assert simulation_projet.taux == 30


def test_incoherent_new_montant_and_new_taux(simulation_projet, initial_data):
    data = initial_data
    data["montant"] = 400
    data["taux"] = 30  # will be ignored

    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["montant"] == 400
    assert form.cleaned_data["taux"] == 40
    form.save()
    assert simulation_projet.montant == 400
    assert simulation_projet.taux == 40


def test_incoherent_new_assiette_and_new_taux(simulation_projet, initial_data):
    data = initial_data
    data["assiette"] = 2_000
    data["taux"] = 30  # will be ignored

    form = SimulationProjetForm(instance=simulation_projet, data=data)

    assert form.is_valid()
    assert form.cleaned_data["assiette"] == 2_000
    assert form.cleaned_data["montant"] == 200
    assert form.cleaned_data["taux"] == 10
    form.save()
    assert simulation_projet.dotation_projet.assiette == 2_000
    assert simulation_projet.montant == 200
    assert simulation_projet.taux == 10


def test_assiette_cant_be_higher_than_cout_total(simulation_projet):
    simulation_projet.dotation_projet.projet.dossier_ds.finance_cout_total = 1_000
    simulation_projet.dotation_projet.projet.dossier_ds.save()
    data = {
        "assiette": 2_000,
        "montant": 200,
        "taux": 13,
    }
    form = SimulationProjetForm(instance=simulation_projet, data=data)
    assert not form.is_valid()
    assert list(form.errors.keys()) == ["assiette"]
    assert form.errors["assiette"] == [
        "L'assiette ne doit pas être supérieure au coût total du projet."
    ]


def test_montant_cant_be_higher_than_assiette(simulation_projet):
    data = {"assiette": 1_000, "montant": 2_000, "taux": 10}
    form = SimulationProjetForm(instance=simulation_projet, data=data)
    assert not form.is_valid()
    assert list(form.errors.keys()) == ["montant"]
    assert (
        "Le montant de la simulation ne peut pas être supérieur à l'assiette du projet"
        in form.errors["montant"][0]
    )
