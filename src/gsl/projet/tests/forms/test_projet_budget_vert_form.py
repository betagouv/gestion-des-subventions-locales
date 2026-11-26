from unittest.mock import patch

import pytest

from dn.sync.models import Dotation
from dn.sync.services import DsService
from gsl.core.tests.factories import CollegueWithDSProfileFactory
from gsl.historique.models import ProjetAction

from ...forms import ProjetBudgetVertForm
from ..factories import EnveloppeProjetFactory, ProjetFactory


@pytest.fixture
def projet():
    projet = ProjetFactory(
        is_in_qpv=False, is_attached_to_a_crte=False, is_budget_vert=False
    )
    EnveloppeProjetFactory(projet=projet, dotation=Dotation.DETR)
    return projet


@pytest.fixture
def user():
    return CollegueWithDSProfileFactory()


@patch.object(DsService, "update_annotations")
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
    assert mock_update_annotations.call_args.kwargs["annotations"] == {
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


@patch.object(DsService, "update_annotations")
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
