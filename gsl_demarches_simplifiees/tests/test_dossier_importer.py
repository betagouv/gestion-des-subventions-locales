from unittest.mock import patch

import pytest
from django.contrib import messages
from django.utils.timezone import datetime

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier import (
    refresh_dossier_instructeurs,
    save_one_dossier_from_ds,
)
from gsl_demarches_simplifiees.models import Profile
from gsl_demarches_simplifiees.tests.factories import DossierFactory


def test_save_one_dossier_from_ds_error_with_invalid_ds_response():
    ds_client = DsClient()
    dossier = DossierFactory.build()
    with patch.object(
        ds_client,
        "get_one_dossier",
        return_value={"no_date_in_result": "so_raise_an_exception"},
    ):
        with pytest.raises(DsServiceException):
            save_one_dossier_from_ds(dossier, ds_client)


def test_save_one_dossier_from_ds_no_need_to_update():
    ds_client = DsClient()
    date_in_ds_and_dossier = "2024-10-16T10:09:33+02:00"
    dossier = DossierFactory.build(
        ds_date_derniere_modification=datetime.fromisoformat(date_in_ds_and_dossier)
    )
    with patch.object(
        ds_client,
        "get_one_dossier",
        return_value={"dateDerniereModification": date_in_ds_and_dossier},
    ):
        level, message = save_one_dossier_from_ds(dossier, ds_client)
        assert level == messages.WARNING
        assert "Le dossier était déjà à jour sur Turgot" in message


def test_save_one_dossier_from_ds_should_be_updated():
    ds_client = DsClient()
    date_in_ds = "2025-10-16T10:09:33+02:00"
    date_in_turgot = "2024-10-16T10:09:33+02:00"
    dossier = DossierFactory.build(
        ds_date_derniere_modification=datetime.fromisoformat(date_in_turgot)
    )
    with patch.object(
        ds_client,
        "get_one_dossier",
        return_value={"dateDerniereModification": date_in_ds},
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
        ) as target_task:
            level, message = save_one_dossier_from_ds(dossier, ds_client)
            assert level == messages.SUCCESS
            assert "Le dossier a bien été mis à jour" in message
            target_task.assert_called_once()


@pytest.mark.django_db
def test_refresh_dossier_instructeurs():
    dossier = DossierFactory()

    # Existing instructeurs A and B
    profile_a = Profile.objects.create(ds_id="A-1", ds_email="a@example.com")
    profile_b = Profile.objects.create(ds_id="B-2", ds_email="b@example.com")
    dossier.ds_instructeurs.add(profile_a, profile_b)

    # Incoming DS data contains B (kept) and C (new); A should be removed
    ds_payload = {
        "groupeInstructeur": {
            "instructeurs": [
                {"id": profile_b.ds_id, "email": profile_b.ds_email},
                {"id": "C-3", "email": "c@example.com"},
            ]
        }
    }

    # First refresh: remove A, keep B, add C
    refresh_dossier_instructeurs(ds_payload, dossier)

    current_ids = set(dossier.ds_instructeurs.values_list("ds_id", flat=True))
    assert current_ids == {"B-2", "C-3"}

    # Ensure C profile was created with correct attributes
    c_profile = Profile.objects.get(ds_id="C-3")
    assert c_profile.ds_email == "c@example.com"

    # Second refresh with the same payload should be a no-op (no duplicates, same set)
    refresh_dossier_instructeurs(ds_payload, dossier)
    current_ids_again = set(dossier.ds_instructeurs.values_list("ds_id", flat=True))
    assert current_ids_again == {"B-2", "C-3"}
    assert dossier.ds_instructeurs.count() == 2
