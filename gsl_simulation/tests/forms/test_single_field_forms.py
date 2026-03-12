from typing import cast
from unittest import mock

import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import CollegueFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import PROJET_STATUS_ACCEPTED
from gsl_projet.tests.factories import DetrProjetFactory, DotationProjetFactory
from gsl_simulation.forms import (
    AssietteSingleFieldForm,
    MontantSingleFieldForm,
    TauxSingleFieldForm,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> Collegue:
    return cast(Collegue, CollegueFactory())


# -- AssietteSingleFieldForm: assiette validation (via DotationProjet.clean_fields) --


def test_clean_assiette_rejects_above_cout_total(user):
    dotation_projet = DetrProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
        detr_avis_commission=None,
    )
    simulation_projet = SimulationProjetFactory(dotation_projet=dotation_projet)
    form = AssietteSingleFieldForm(
        data={"assiette": 100_001},
        instance=dotation_projet,
        simulation_projet=simulation_projet,
        user=user,
    )
    assert not form.is_valid()
    assert "assiette" in form.errors


def test_clean_assiette_accepts_within_cout_total(user):
    dotation_projet = DetrProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
        detr_avis_commission=None,
    )
    simulation_projet = SimulationProjetFactory(dotation_projet=dotation_projet)
    form = AssietteSingleFieldForm(
        data={"assiette": 100_000},
        instance=dotation_projet,
        simulation_projet=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors


# -- AssietteSingleFieldForm.save (accepted) --


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_assiette_form_save_accepted_triggers_accept(mock_ds_update, user):
    dotation_projet = DetrProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
        detr_avis_commission=None,
        assiette=80_000,
        status=PROJET_STATUS_ACCEPTED,
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=40_000,
    )
    ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe.delegation_root,
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=40_000,
    )

    form = AssietteSingleFieldForm(
        data={"assiette": 90_000},
        instance=dotation_projet,
        simulation_projet=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors
    form.save()

    mock_ds_update.assert_called_once()
    call_kwargs = mock_ds_update.call_args.kwargs
    assert call_kwargs["assiette"] == 90_000
    assert call_kwargs["montant"] == 40_000


# -- MontantSingleFieldForm.clean_montant --


def test_clean_montant_rejects_above_assiette(user):
    dotation_projet = DotationProjetFactory(assiette=100)
    simulation_projet = SimulationProjetFactory(dotation_projet=dotation_projet)
    form = MontantSingleFieldForm(
        data={"montant": 101},
        instance=simulation_projet,
        user=user,
    )
    assert not form.is_valid()
    assert "montant" in form.errors


def test_clean_montant_accepts_within_assiette(user):
    dotation_projet = DotationProjetFactory(assiette=100)
    simulation_projet = SimulationProjetFactory(dotation_projet=dotation_projet)
    form = MontantSingleFieldForm(
        data={"montant": 100},
        instance=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors


# -- MontantSingleFieldForm.save --


def test_montant_form_save_updates_montant(user):
    dotation_projet = DotationProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        montant=1000,
    )
    form = MontantSingleFieldForm(
        data={"montant": 500},
        instance=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors
    form.save()
    simulation_projet.refresh_from_db()
    assert simulation_projet.montant == 500
    assert simulation_projet.taux == 50


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_montant_form_save_accepted_triggers_accept(mock_ds_update, user):
    dotation_projet = DotationProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )
    ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe.delegation_root,
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )

    form = MontantSingleFieldForm(
        data={"montant": 500},
        instance=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors
    form.save()

    mock_ds_update.assert_called_once()
    call_kwargs = mock_ds_update.call_args.kwargs
    assert call_kwargs["montant"] == 500
    assert call_kwargs["assiette"] == 1000

    simulation_projet.refresh_from_db()
    assert simulation_projet.montant == 500


# -- TauxSingleFieldForm --


def test_taux_form_rejects_above_100(user):
    dotation_projet = DotationProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet, montant=100
    )
    form = TauxSingleFieldForm(
        data={"taux": 101},
        instance=simulation_projet,
        user=user,
    )
    assert not form.is_valid()
    assert "taux" in form.errors


def test_taux_form_rejects_below_0(user):
    dotation_projet = DotationProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet, montant=100
    )
    form = TauxSingleFieldForm(
        data={"taux": -1},
        instance=simulation_projet,
        user=user,
    )
    assert not form.is_valid()
    assert "taux" in form.errors


# -- TauxSingleFieldForm.save --


def test_taux_form_save_updates_montant_from_taux(user):
    dotation_projet = DotationProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        montant=100,
    )
    form = TauxSingleFieldForm(
        data={"taux": 15},
        instance=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors
    form.save()
    simulation_projet.refresh_from_db()
    assert simulation_projet.montant == 150


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_taux_form_save_accepted_triggers_accept(mock_ds_update, user):
    dotation_projet = DotationProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=200,
    )
    ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe.delegation_root,
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )

    form = TauxSingleFieldForm(
        data={"taux": 15},
        instance=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors
    form.save()

    mock_ds_update.assert_called_once()
    call_kwargs = mock_ds_update.call_args.kwargs
    assert call_kwargs["montant"] == 150
    assert call_kwargs["assiette"] == 1000

    simulation_projet.refresh_from_db()
    assert simulation_projet.montant == 150
