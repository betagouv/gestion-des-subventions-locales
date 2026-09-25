from typing import cast
from unittest import mock

import pytest

from gsl.core.models import Collegue
from gsl.core.tests.factories import CollegueFactory
from gsl.projet.constants import ProjetStatus
from gsl.projet.tests.factories import DetrProjetFactory, EnveloppeProjetFactory

from ...forms import (
    AssietteSingleFieldForm,
    MontantSingleFieldForm,
    TauxSingleFieldForm,
)
from ...models import SimulationProjet
from ..factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> Collegue:
    return cast(Collegue, CollegueFactory())


# -- AssietteSingleFieldForm: assiette validation (via EnveloppeProjet.clean_fields) --


def test_clean_assiette_rejects_above_cout_total(user):
    enveloppe_projet = DetrProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
        detr_avis_commission=None,
    )
    simulation_projet = SimulationProjetFactory(enveloppe_projet=enveloppe_projet)
    form = AssietteSingleFieldForm(
        data={"assiette": 100_001},
        instance=enveloppe_projet,
        simulation_projet=simulation_projet,
        user=user,
    )
    assert not form.is_valid()
    assert "assiette" in form.errors


def test_clean_assiette_accepts_within_cout_total(user):
    enveloppe_projet = DetrProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
        detr_avis_commission=None,
    )
    simulation_projet = SimulationProjetFactory(enveloppe_projet=enveloppe_projet)
    form = AssietteSingleFieldForm(
        data={"assiette": 100_000},
        instance=enveloppe_projet,
        simulation_projet=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors


# -- AssietteSingleFieldForm.save (accepted) --


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_assiette_form_save_accepted_triggers_accept(mock_ds_update, user):
    enveloppe_projet = DetrProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
        detr_avis_commission=None,
        assiette=80_000,
        status=ProjetStatus.ACCEPTED,
    )
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=40_000,
    )
    enveloppe_projet.accept_without_ds_update(
        montant=40_000, enveloppe=simulation_projet.enveloppe.delegation_root
    )
    enveloppe_projet.save()

    form = AssietteSingleFieldForm(
        data={"assiette": 90_000},
        instance=enveloppe_projet,
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
    enveloppe_projet = EnveloppeProjetFactory(assiette=100)
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    form = MontantSingleFieldForm(
        data={"montant": 101},
        instance=simulation_projet,
        user=user,
    )
    assert not form.is_valid()
    assert "__all__" in form.errors


def test_clean_montant_accepts_within_assiette(user):
    enveloppe_projet = EnveloppeProjetFactory(assiette=100)
    simulation_projet = SimulationProjetFactory(enveloppe_projet=enveloppe_projet)
    form = MontantSingleFieldForm(
        data={"montant": 100},
        instance=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors


# -- MontantSingleFieldForm.save --


def test_montant_form_save_updates_montant(user):
    enveloppe_projet = EnveloppeProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
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
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=1000, status=ProjetStatus.PROCESSING
    )
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )
    enveloppe_projet.accept_without_ds_update(
        montant=1_000, enveloppe=simulation_projet.enveloppe.delegation_root
    )
    enveloppe_projet.save()

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


def test_taux_form_accepts_when_old_montant_above_assiette(user):
    """Remplir le taux doit être valide même si l'ancien montant dépasse l'assiette."""
    enveloppe_projet = EnveloppeProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        montant=2000,  # montant > assiette : état invalide à corriger
    )
    form = TauxSingleFieldForm(
        data={"taux": 10},  # 10% de 1000 = 100, ce qui est valide
        instance=simulation_projet,
        user=user,
    )
    assert form.is_valid(), form.errors


def test_taux_form_rejects_above_100(user):
    enveloppe_projet = EnveloppeProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet, montant=100
    )
    form = TauxSingleFieldForm(
        data={"taux": 101},
        instance=simulation_projet,
        user=user,
    )
    assert not form.is_valid()
    assert "taux" in form.errors


def test_taux_form_rejects_below_0(user):
    enveloppe_projet = EnveloppeProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet, montant=100
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
    enveloppe_projet = EnveloppeProjetFactory(assiette=1000)
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
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
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=1000, status=ProjetStatus.PROCESSING
    )
    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=200,
    )
    enveloppe_projet.accept_without_ds_update(
        montant=200, enveloppe=simulation_projet.enveloppe.delegation_root
    )
    enveloppe_projet.save()

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
