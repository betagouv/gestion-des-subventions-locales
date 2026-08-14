import logging
from unittest.mock import patch

import pytest
from django import forms

from gsl_core.tests.factories import CollegueWithDSProfileFactory
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.services import DsService
from gsl_historique.models import ProjetAction
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.forms import ProjetBudgetVertForm, ProjetForm
from gsl_projet.models import DotationProjet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory


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
    assert list(form.fields.keys()) == ["dotations"]
    dotations = form.fields["dotations"]
    assert isinstance(dotations, forms.MultipleChoiceField)
    assert dotations.required is False


@pytest.mark.django_db
def test_projet_form_validation(projet):
    form = ProjetForm(instance=projet, data={"dotations": [DOTATION_DSIL]})
    assert form.is_valid()

    form = ProjetForm(instance=projet, data={"dotations": []})
    assert not form.is_valid()
    assert "dotations" in form.errors


@patch.object(DsService, "update_checkboxes_annotations")
@pytest.mark.django_db
def test_projet_budget_vert_form_save(mock_update_annotations, projet, user):
    assert projet.is_budget_vert is False

    form = ProjetBudgetVertForm(
        instance=projet, data={"is_budget_vert": "on"}, user=user
    )
    assert form.is_valid()
    form.save(commit=True)

    projet.refresh_from_db()
    assert projet.is_budget_vert is True

    # Only the budget vert annotation is pushed to DN
    mock_update_annotations.assert_called_once()
    assert mock_update_annotations.call_args.kwargs["annotations_to_update"] == {
        "annotations_is_budget_vert": True
    }

    # The change is recorded in the projet history
    action = ProjetAction.objects.get(
        projet=projet, action_type=ProjetAction.TYPE_BOOLEAN_MODIFIED
    )
    assert (
        action.boolean_field
        == "Projet concourant à la transition écologique au sens budget vert"
    )
    assert action.boolean_value is True


@patch.object(DsService, "update_checkboxes_annotations")
@pytest.mark.django_db
def test_projet_budget_vert_form_save_unchanged_is_a_noop(
    mock_update_annotations, projet, user
):
    form = ProjetBudgetVertForm(instance=projet, data={"is_budget_vert": ""}, user=user)
    assert form.is_valid()
    form.save(commit=True)

    projet.refresh_from_db()
    assert projet.is_budget_vert is False
    # Nothing changed: no DN push, no history entry
    mock_update_annotations.assert_not_called()
    assert not ProjetAction.objects.filter(
        projet=projet, action_type=ProjetAction.TYPE_BOOLEAN_MODIFIED
    ).exists()


@pytest.mark.django_db
def test_projet_form_save_with_multiple_dotations(projet):
    data = {"dotations": [DOTATION_DSIL, DOTATION_DETR]}
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    projet = form.save(commit=True)

    assert DOTATION_DSIL in projet.dotations
    assert DOTATION_DETR in projet.dotations


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


# update_dotation tests


@pytest.fixture
def projet_0():
    return ProjetFactory()


@pytest.mark.django_db
def test_update_dotation_with_no_value(projet_0, user, caplog):
    with caplog.at_level(logging.WARNING):
        form = ProjetForm(instance=projet_0, data={"dotations": []}, user=user)
        form.update_dotation(projet_0, [], user)

    assert form.errors["dotations"] == ["Le projet doit avoir au moins une dotation."]
    assert "Projet must have at least one dotation" in caplog.text


@pytest.mark.django_db
def test_update_dotation_with_more_than_2_values(projet_0, user, caplog):
    with caplog.at_level(logging.WARNING):
        form = ProjetForm(
            instance=projet_0,
            data={"dotations": [DOTATION_DETR, DOTATION_DSIL, "unknown"]},
            user=user,
        )
        form.update_dotation(projet_0, [DOTATION_DETR, DOTATION_DSIL, "unknown"], user)
    assert "Le projet ne peut avoir plus de deux dotations." in form.errors["dotations"]
    assert "Projet can't have more than two dotations" in caplog.text


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DotationProjetService, "create_simulation_projets_from_dotation_projet")
@pytest.mark.django_db
def test_update_dotation_from_one_dotation_to_another(
    mock_create_simulation_projets, dotation, projet_0, user
):
    original_dotation_projet = DotationProjetFactory(
        projet=projet_0, dotation=dotation, status=PROJET_STATUS_PROCESSING
    )
    SimulationProjetFactory.create_batch(3, dotation_projet=original_dotation_projet)
    ProgrammationProjetFactory.create(dotation_projet=original_dotation_projet)

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    form = ProjetForm(instance=projet_0, data={"dotations": [new_dotation]}, user=user)
    form.update_dotation(projet_0, [new_dotation], user)

    assert projet_0.dotations == [new_dotation]
    assert projet_0.dotationprojet_set.count() == 1
    dotation_projet = projet_0.dotationprojet_set.first()

    assert mock_create_simulation_projets.call_count == 1
    mock_create_simulation_projets.assert_called_once_with(dotation_projet)

    # Check that the old dotation_projet is deleted
    assert DotationProjet.objects.filter(pk=original_dotation_projet.pk).count() == 0
    assert SimulationProjet.objects.count() == 0
    assert ProgrammationProjet.objects.count() == 0


@pytest.mark.parametrize("original_dotation", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DotationProjetService, "create_simulation_projets_from_dotation_projet")
@pytest.mark.django_db
def test_update_dotation_from_one_to_two(
    mock_create_simulation_projets, original_dotation, projet_0, user
):
    original_dotation_projet = DotationProjetFactory(
        projet=projet_0, dotation=original_dotation
    )
    SimulationProjetFactory.create_batch(3, dotation_projet=original_dotation_projet)
    ProgrammationProjetFactory.create(dotation_projet=original_dotation_projet)

    form = ProjetForm(
        instance=projet_0, data={"dotations": [DOTATION_DETR, DOTATION_DSIL]}, user=user
    )
    form.update_dotation(projet_0, [DOTATION_DETR, DOTATION_DSIL], user)

    assert projet_0.dotationprojet_set.count() == 2
    assert all(
        dotation in projet_0.dotations for dotation in {DOTATION_DETR, DOTATION_DSIL}
    )
    new_dotation_projet = projet_0.dotationprojet_set.exclude(
        pk=original_dotation_projet.pk
    ).first()
    mock_create_simulation_projets.assert_called_once_with(new_dotation_projet)
    assert new_dotation_projet.status == PROJET_STATUS_PROCESSING
    assert new_dotation_projet.assiette is None
    assert new_dotation_projet.detr_avis_commission is None


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_accepted_dotation_calls_ds_service(
    mock_update_ds_annotations,
    dotation,
    projet_0,
    user,
):
    """Test that removing an ACCEPTED dotation_projet calls DS service"""
    accepted_dotation_projet = DotationProjetFactory(
        projet=projet_0, dotation=dotation, status=PROJET_STATUS_ACCEPTED
    )

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    form = ProjetForm(instance=projet_0, data={"dotations": [new_dotation]}, user=user)
    form.update_dotation(projet_0, [new_dotation], user)

    # Verify DS service was called with correct parameters
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet_0.dossier_ds,
        user=user,
        dotations_to_be_checked=accepted_dotation_projet.other_accepted_dotations,
    )

    # Verify the dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=accepted_dotation_projet.pk).count() == 0


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_processing_dotation_no_ds_service_call(
    mock_update_ds_annotations,
    dotation,
    projet_0,
    user,
):
    """Test that removing a PROCESSING dotation_projet does NOT call DS service"""
    processing_dotation_projet = DotationProjetFactory(
        projet=projet_0, dotation=dotation, status=PROJET_STATUS_PROCESSING
    )

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    form = ProjetForm(instance=projet_0, data={"dotations": [new_dotation]}, user=user)
    form.update_dotation(projet_0, [new_dotation], user)

    # Verify DS service was NOT called
    mock_update_ds_annotations.assert_not_called()

    # Verify the dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=processing_dotation_projet.pk).count() == 0


@pytest.mark.parametrize("dotation_to_remove", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_accepted_dotation_keeps_other_accepted_dotations_in_dn(
    mock_update_ds_annotations,
    dotation_to_remove,
    projet_0,
    user,
):
    """Test that removing an ACCEPTED dotation_projet passes other_accepted_dotations correctly"""
    # Create two accepted dotations
    dotation_to_keep = (
        DOTATION_DSIL if dotation_to_remove == DOTATION_DETR else DOTATION_DETR
    )
    accepted_dotation_to_remove = DotationProjetFactory(
        projet=projet_0, dotation=dotation_to_remove, status=PROJET_STATUS_ACCEPTED
    )
    accepted_dotation_to_keep = DotationProjetFactory(
        projet=projet_0, dotation=dotation_to_keep, status=PROJET_STATUS_ACCEPTED
    )

    # Remove one dotation
    form = ProjetForm(
        instance=projet_0, data={"dotations": [dotation_to_keep]}, user=user
    )
    form.update_dotation(projet_0, [dotation_to_keep], user)

    # Verify DS service was called with the other accepted dotation
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet_0.dossier_ds,
        user=user,
        dotations_to_be_checked=[dotation_to_keep],
    )

    # Verify the removed dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_remove.pk).count() == 0
    # Verify the kept dotation_projet still exists
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_keep.pk).count() == 1


@pytest.mark.parametrize("dotation_to_remove", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_removes_accepted_dotation_with_processing_dotation(
    mock_update_ds_annotations,
    dotation_to_remove,
    projet_0,
    user,
):
    """Test that removing an ACCEPTED dotation_projet ignores PROCESSING dotations in other_accepted_dotations"""
    # Create one accepted and one processing dotation
    dotation_to_keep = (
        DOTATION_DSIL if dotation_to_remove == DOTATION_DETR else DOTATION_DETR
    )
    accepted_dotation_to_remove = DotationProjetFactory(
        projet=projet_0, dotation=dotation_to_remove, status=PROJET_STATUS_ACCEPTED
    )
    processing_dotation_to_keep = DotationProjetFactory(
        projet=projet_0, dotation=dotation_to_keep, status=PROJET_STATUS_PROCESSING
    )

    # Remove the accepted dotation
    form = ProjetForm(
        instance=projet_0, data={"dotations": [dotation_to_keep]}, user=user
    )
    form.update_dotation(projet_0, [dotation_to_keep], user)

    # Verify DS service was called with empty list (no other accepted dotations)
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet_0.dossier_ds,
        user=user,
        dotations_to_be_checked=[],
    )

    # Verify the removed dotation_projet was deleted
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_remove.pk).count() == 0
    # Verify the kept dotation_projet still exists
    assert DotationProjet.objects.filter(pk=processing_dotation_to_keep.pk).count() == 1


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DotationProjetService, "create_simulation_projets_from_dotation_projet")
@pytest.mark.django_db
def test_update_dotation_sets_dotations_has_been_updated_when_adding_dotation(
    mock_create_simulation_projets, dotation, projet_0, user
):
    """Test that dotations_updated_in_app is set to True when adding a new dotation"""
    DotationProjetFactory(projet=projet_0, dotation=dotation)
    assert projet_0.dotations_updated_in_app is False

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    form = ProjetForm(
        instance=projet_0, data={"dotations": [dotation, new_dotation]}, user=user
    )
    form.update_dotation(projet_0, [dotation, new_dotation], user)

    projet_0.refresh_from_db()
    assert projet_0.dotations_updated_in_app is True


@pytest.mark.parametrize("dotation", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_sets_dotations_has_been_updated_when_removing_dotation(
    mock_update_ds_annotations, dotation, projet_0, user
):
    """Test that dotations_updated_in_app is set to True when removing a dotation"""
    DotationProjetFactory(
        projet=projet_0, dotation=dotation, status=PROJET_STATUS_PROCESSING
    )
    assert projet_0.dotations_updated_in_app is False

    new_dotation = DOTATION_DSIL if dotation == DOTATION_DETR else DOTATION_DETR
    form = ProjetForm(instance=projet_0, data={"dotations": [new_dotation]}, user=user)
    form.update_dotation(projet_0, [new_dotation], user)

    projet_0.refresh_from_db()
    assert projet_0.dotations_updated_in_app is True


@pytest.mark.django_db
def test_update_dotation_does_not_set_dotations_has_been_updated_when_unchanged(
    projet_0, user
):
    """Test that dotations_updated_in_app stays False when dotations are unchanged"""
    DotationProjetFactory(projet=projet_0, dotation=DOTATION_DETR)
    projet_0.dotations_updated_in_app = False
    projet_0.save()
    assert projet_0.dotations_updated_in_app is False

    form = ProjetForm(instance=projet_0, data={"dotations": [DOTATION_DETR]}, user=user)
    form.update_dotation(projet_0, [DOTATION_DETR], user)

    projet_0.refresh_from_db()
    assert projet_0.dotations_updated_in_app is False


@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@patch.object(DotationProjetService, "create_simulation_projets_from_dotation_projet")
@pytest.mark.django_db
def test_projet_form_save_sets_dotations_has_been_updated_when_dotations_change(
    mock_create_simulation_projets,
    _mock_update_ds_annotations,
    projet,
    user,
):
    """Test that ProjetForm.save() sets dotations_updated_in_app when dotations change"""
    # projet fixture has DETR, we change to DSIL
    assert projet.dotations == [DOTATION_DETR]
    assert projet.dotations_updated_in_app is False

    form = ProjetForm(instance=projet, data={"dotations": [DOTATION_DSIL]}, user=user)
    assert form.is_valid()

    form.save(commit=True)

    projet.refresh_from_db()
    assert projet.dotations == [DOTATION_DSIL]
    assert projet.dotations_updated_in_app is True


@pytest.mark.parametrize("dotation_to_remove", [DOTATION_DETR, DOTATION_DSIL])
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_update_dotation_with_dn_error_cancel_update(
    mock_update_ds_annotations,
    dotation_to_remove,
    projet_0,
    user,
):
    """Test that removing an ACCEPTED dotation_projet cancels the update if there is an error in the DS service"""
    # Create one accepted and one processing dotation
    dotation_to_keep = (
        DOTATION_DSIL if dotation_to_remove == DOTATION_DETR else DOTATION_DETR
    )
    accepted_dotation_to_remove = DotationProjetFactory(
        projet=projet_0, dotation=dotation_to_remove, status=PROJET_STATUS_ACCEPTED
    )
    processing_dotation_to_keep = DotationProjetFactory(
        projet=projet_0, dotation=dotation_to_keep, status=PROJET_STATUS_PROCESSING
    )
    mock_update_ds_annotations.side_effect = DsServiceException("Error in DS service")

    # Remove the accepted dotation
    with pytest.raises(DsServiceException):
        form = ProjetForm(
            instance=projet_0, data={"dotations": [dotation_to_keep]}, user=user
        )
        form.update_dotation(projet_0, [dotation_to_keep], user)

    # Verify DS service was called with empty list (no other accepted dotations)
    mock_update_ds_annotations.assert_called_once_with(
        dossier=projet_0.dossier_ds,
        user=user,
        dotations_to_be_checked=[],
    )

    # Verify the removed dotation_projet still exists
    assert DotationProjet.objects.filter(pk=accepted_dotation_to_remove.pk).count() == 1
    # Verify the kept dotation_projet still exists
    assert DotationProjet.objects.filter(pk=processing_dotation_to_keep.pk).count() == 1
