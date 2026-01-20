import logging
from unittest.mock import patch

import pytest
from django import forms

from gsl_core.tests.factories import CollegueWithDSProfileFactory
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.services import DsService
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.forms import ProjetForm
from gsl_projet.models import DotationProjet, Projet
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

    expected_fields = [
        "is_budget_vert",
        "is_in_qpv",
        "is_attached_to_a_crte",
        "is_frr",
        "is_acv",
        "is_pvd",
        "is_va",
        "is_autre_zonage_local",
        "autre_zonage_local",
        "is_contrat_local",
        "contrat_local",
        "dotations",
    ]
    assert list(form.fields.keys()) == expected_fields

    budget_field = form.fields["is_budget_vert"]
    assert isinstance(budget_field, forms.BooleanField)
    assert budget_field.required is False
    assert (
        budget_field.label
        == "Projet concourant à la transition écologique au sens budget vert"
    )

    budget_field = form.fields["is_in_qpv"]
    assert isinstance(budget_field, forms.BooleanField)
    assert budget_field.required is False
    assert budget_field.label == "Projet situé en QPV"

    is_attached_to_a_crte = form.fields["is_attached_to_a_crte"]
    assert isinstance(is_attached_to_a_crte, forms.BooleanField)
    assert is_attached_to_a_crte.required is False

    autre_zonage_local = form.fields["autre_zonage_local"]
    assert isinstance(autre_zonage_local, forms.CharField)
    assert autre_zonage_local.required is False
    assert autre_zonage_local.label == "Nom du zonage local"

    contrat_local = form.fields["contrat_local"]
    assert isinstance(contrat_local, forms.CharField)
    assert contrat_local.required is False
    assert contrat_local.label == "Nom du contrat local"

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
    assert "dotations" in form.errors

    # BooleanField cast string value to boolean
    assert "is_budget_vert" not in form.errors
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
def test_autre_zonage_local_required_when_checkbox_checked(projet):
    """Test that autre_zonage_local is required when is_autre_zonage_local is True"""
    data = {
        "is_autre_zonage_local": True,
        "autre_zonage_local": "",  # Empty value
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert not form.is_valid()
    assert "autre_zonage_local" in form.errors
    assert (
        "Ce champ est obligatoire si le projet est rattaché à un autre zonage local."
        in form.errors["autre_zonage_local"]
    )


@pytest.mark.django_db
def test_autre_zonage_local_not_required_when_checkbox_unchecked(projet):
    """Test that autre_zonage_local is not required when is_autre_zonage_local is False"""
    data = {
        "is_autre_zonage_local": False,
        "autre_zonage_local": "",  # Empty value is OK
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    projet = form.save(commit=False)
    assert projet.autre_zonage_local == ""


@pytest.mark.django_db
def test_autre_zonage_local_cleared_when_checkbox_unchecked(projet):
    """Test that autre_zonage_local is cleared when is_autre_zonage_local is unchecked"""
    projet.autre_zonage_local = "Zonage ABC"
    projet.save()

    data = {
        "is_autre_zonage_local": False,
        "autre_zonage_local": "Zonage ABC",  # Value provided but checkbox unchecked
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    projet = form.save(commit=False)
    assert projet.autre_zonage_local == ""


@pytest.mark.django_db
def test_contrat_local_required_when_checkbox_checked(projet):
    """Test that contrat_local is required when is_contrat_local is True"""
    data = {
        "is_contrat_local": True,
        "contrat_local": "",  # Empty value
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert not form.is_valid()
    assert "contrat_local" in form.errors
    assert (
        "Ce champ est obligatoire si le projet est rattaché à un contrat local."
        in form.errors["contrat_local"]
    )


@pytest.mark.django_db
def test_contrat_local_not_required_when_checkbox_unchecked(projet):
    """Test that contrat_local is not required when is_contrat_local is False"""
    data = {
        "is_contrat_local": False,
        "contrat_local": "",  # Empty value is OK
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    projet = form.save(commit=False)
    assert projet.contrat_local == ""


@pytest.mark.django_db
def test_contrat_local_cleared_when_checkbox_unchecked(projet):
    """Test that contrat_local is cleared when is_contrat_local is unchecked"""
    projet.contrat_local = "Contrat XYZ"
    projet.save()

    data = {
        "is_contrat_local": False,
        "contrat_local": "Contrat XYZ",  # Value provided but checkbox unchecked
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    projet = form.save(commit=False)
    assert projet.contrat_local == ""


@patch.object(DsService, "update_checkboxes_annotations")
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_projet_form_save(
    _mock_update_ds_annotations, mock_update_checkboxes_annotations, projet, user
):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "is_budget_vert": False,
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data, user=user)
    assert form.is_valid()

    projet = form.save(commit=True)

    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is True
    assert projet.is_attached_to_a_crte is True
    assert projet.is_budget_vert is False
    assert projet.dotations == [DOTATION_DSIL]

    # Verify DN synchronization was called
    mock_update_checkboxes_annotations.assert_called_once()
    call_kwargs = mock_update_checkboxes_annotations.call_args.kwargs
    assert call_kwargs["dossier"] == projet.dossier_ds
    assert call_kwargs["user"] == user
    assert "annotations_to_update" in call_kwargs
    assert "text_annotations_to_update" in call_kwargs


@patch.object(DsService, "update_checkboxes_annotations")
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_projet_form_save_with_autre_zonage_local(
    _mock_update_ds_annotations, mock_update_checkboxes_annotations, projet, user
):
    """Test saving projet with autre_zonage_local and synchronization to DN"""
    data = {
        "is_autre_zonage_local": True,
        "autre_zonage_local": "Zonage Test ABC",
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data, user=user)
    assert form.is_valid()

    projet = form.save(commit=True)

    assert isinstance(projet, Projet)
    assert projet.is_autre_zonage_local is True
    assert projet.autre_zonage_local == "Zonage Test ABC"

    # Verify DN synchronization was called with correct values
    mock_update_checkboxes_annotations.assert_called_once()
    call_kwargs = mock_update_checkboxes_annotations.call_args.kwargs
    assert (
        call_kwargs["annotations_to_update"]["annotations_is_autre_zonage_local"]
        is True
    )
    assert (
        call_kwargs["text_annotations_to_update"]["annotations_autre_zonage_local"]
        == "Zonage Test ABC"
    )


@patch.object(DsService, "update_checkboxes_annotations")
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_projet_form_save_with_contrat_local(
    _mock_update_ds_annotations, mock_update_checkboxes_annotations, projet, user
):
    """Test saving projet with contrat_local and synchronization to DN"""
    data = {
        "is_contrat_local": True,
        "contrat_local": "Contrat Test XYZ",
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data, user=user)
    assert form.is_valid()

    projet = form.save(commit=True)

    assert isinstance(projet, Projet)
    assert projet.is_contrat_local is True
    assert projet.contrat_local == "Contrat Test XYZ"

    # Verify DN synchronization was called with correct values
    mock_update_checkboxes_annotations.assert_called_once()
    call_kwargs = mock_update_checkboxes_annotations.call_args.kwargs
    assert call_kwargs["annotations_to_update"]["annotations_is_contrat_local"] is True
    assert (
        call_kwargs["text_annotations_to_update"]["annotations_contrat_local"]
        == "Contrat Test XYZ"
    )


@patch.object(DsService, "update_checkboxes_annotations")
@patch.object(DsService, "update_ds_annotations_for_one_dotation")
@pytest.mark.django_db
def test_projet_form_save_with_both_text_fields(
    _mock_update_ds_annotations, mock_update_checkboxes_annotations, projet, user
):
    """Test saving projet with both autre_zonage_local and contrat_local"""
    data = {
        "is_autre_zonage_local": True,
        "autre_zonage_local": "Zonage ABC",
        "is_contrat_local": True,
        "contrat_local": "Contrat XYZ",
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data, user=user)
    assert form.is_valid()

    projet = form.save(commit=True)

    assert isinstance(projet, Projet)
    assert projet.is_autre_zonage_local is True
    assert projet.autre_zonage_local == "Zonage ABC"
    assert projet.is_contrat_local is True
    assert projet.contrat_local == "Contrat XYZ"

    # Verify DN synchronization was called with both text fields
    mock_update_checkboxes_annotations.assert_called_once()
    call_kwargs = mock_update_checkboxes_annotations.call_args.kwargs
    text_annotations = call_kwargs["text_annotations_to_update"]
    assert text_annotations["annotations_autre_zonage_local"] == "Zonage ABC"
    assert text_annotations["annotations_contrat_local"] == "Contrat XYZ"


@pytest.mark.django_db
def test_projet_form_save_with_multiple_dotations(projet):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "is_budget_vert": False,
        "dotations": [DOTATION_DSIL, DOTATION_DETR],
    }
    form = ProjetForm(instance=projet, data=data)
    assert form.is_valid()
    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_checkboxes_annotations"
    ):
        projet = form.save(commit=True)

    assert DOTATION_DSIL in projet.dotations
    assert DOTATION_DETR in projet.dotations


@pytest.mark.django_db
def test_projet_form_save_with_field_exceptions(projet, user):
    data = {
        "is_in_qpv": True,
        "is_attached_to_a_crte": True,
        "is_budget_vert": True,
        "dotations": [DOTATION_DSIL],
    }
    form = ProjetForm(instance=projet, data=data, user=user)
    assert form.is_valid()

    with patch(
        "gsl_demarches_simplifiees.services.DsService.update_checkboxes_annotations"
    ) as mock_update_annotations:
        mock_update_annotations.side_effect = DsServiceException("Some error")
        try:
            projet = form.save(commit=True)
        except DsServiceException as e:
            assert str(e) == "Some error"

    projet.refresh_from_db()
    assert isinstance(projet, Projet)
    assert projet.is_in_qpv is False  # not updated
    assert projet.is_attached_to_a_crte is False  # not updated
    assert projet.is_budget_vert is False  # Default value
    assert projet.dotations == [DOTATION_DETR]  # Default value


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
