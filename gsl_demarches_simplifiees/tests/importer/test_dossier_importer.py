import logging
from unittest.mock import patch

import pytest
from django.contrib import messages
from django.utils.timezone import datetime

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier import (
    _save_dossier_data_and_refresh_dossier_and_projet_and_co,
    refresh_dossier_instructeurs,
    save_demarche_dossiers_from_ds,
    save_one_dossier_from_ds,
)
from gsl_demarches_simplifiees.models import Dossier, Profile
from gsl_demarches_simplifiees.tests.factories import DemarcheFactory, DossierFactory


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_calls_save_dossier_data_and_refresh_dossier_and_projet_and_co():
    demarche_number = 123
    DemarcheFactory(ds_number=demarche_number)
    ds_dossiers = [
        {"id": "DOSS-1", "number": 20240001},
        {"id": "DOSS-2", "number": 20240002},
    ]

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_demarche_dossiers",
        return_value=ds_dossiers,
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._save_dossier_data_and_refresh_dossier_and_projet_and_co"
        ) as target_function:
            save_demarche_dossiers_from_ds(demarche_number)

            assert target_function.call_count == 2
            assert Dossier.objects.filter(ds_id="DOSS-1").exists()
            assert Dossier.objects.filter(ds_id="DOSS-2").exists()
            dossier_1 = Dossier.objects.get(ds_id="DOSS-1")
            assert dossier_1.ds_number == 20240001
            assert dossier_1.ds_demarche.ds_number == demarche_number
            dossier_2 = Dossier.objects.get(ds_id="DOSS-2")
            assert dossier_2.ds_number == 20240002
            assert dossier_2.ds_demarche.ds_number == demarche_number


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_update_raw_ds_data_dossiers():
    demarche_number = 123
    DemarcheFactory(ds_number=demarche_number)

    dossier = DossierFactory(
        ds_id="DOSS-1",
        ds_number=20240001,
        ds_date_derniere_modification="2025-01-01T12:09:33+02:00",
        raw_ds_data={"some_field": "some_value"},
    )

    ds_dossiers = [
        {
            "id": "DOSS-1",
            "number": 20240001,
            "dateDerniereModification": "2025-01-01T12:09:33+02:00",
        },
    ]

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_demarche_dossiers",
        return_value=ds_dossiers,
    ):
        save_demarche_dossiers_from_ds(demarche_number)

        assert Dossier.objects.count() == 1
        dossier.refresh_from_db()

        assert dossier.ds_number == 20240001
        assert dossier.raw_ds_data == ds_dossiers[0]


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_with_one_empty_data(caplog):
    caplog.set_level(logging.INFO)
    demarche_number = 123
    DemarcheFactory(ds_number=demarche_number)

    ds_dossiers = [
        {
            "id": "DOSS-1",
            "number": 20240001,
            "dateDerniereModification": "2025-01-01T12:09:33+02:00",
        },
        None,
        {
            "id": "DOSS-2",
            "number": 20240002,
            "dateDerniereModification": "2025-01-01T12:09:33+02:00",
        },
    ]

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_demarche_dossiers",
        return_value=ds_dossiers,
    ):
        save_demarche_dossiers_from_ds(demarche_number)

        assert Dossier.objects.count() == 2
        assert "Dossier data is empty" in caplog.text


def test_save_demarche_dossiers_from_ds_update_updated_since():
    demarche_number = 123
    demarche = DemarcheFactory(ds_number=demarche_number, updated_since=None)

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_demarche_dossiers",
        return_value=[],
    ):
        save_demarche_dossiers_from_ds(demarche_number)

    demarche.refresh_from_db()
    assert demarche.updated_since is not None
    assert demarche.updated_since > demarche.created_at


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


@pytest.mark.django_db
def test_save_one_dossier_from_ds_no_need_to_update():
    ds_client = DsClient()
    date_in_ds_and_dossier = "2024-10-16T10:09:33+02:00"
    dossier = DossierFactory(
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


@pytest.mark.django_db
def test_save_one_dossier_from_ds_should_be_updated():
    ds_client = DsClient()
    date_in_ds = "2025-10-16T10:09:33+02:00"
    date_in_turgot = "2024-10-16T10:09:33+02:00"
    dossier = DossierFactory(
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


@pytest.mark.django_db
def test_save_dossier_data_and_refresh_dossier_and_projet_and_co_calls_async_task():
    dossier = DossierFactory(
        ds_date_derniere_modification=datetime.fromisoformat(
            "2024-10-16T10:09:33+02:00"
        )
    )
    ds_data = {"dateDerniereModification": "2025-01-01T12:00:00+02:00"}

    with patch(
        "gsl_demarches_simplifiees.tasks.task_refresh_dossier_from_saved_data.delay"
    ) as target_task:
        _save_dossier_data_and_refresh_dossier_and_projet_and_co(
            dossier, ds_data, async_refresh=True
        )
        target_task.assert_called_once_with(dossier.ds_number)


@pytest.mark.django_db
def test_save_dossier_data_and_refresh_dossier_and_projet_and_co_calls_sync_task():
    dossier = DossierFactory(
        ds_date_derniere_modification=datetime.fromisoformat(
            "2024-10-16T10:09:33+02:00"
        )
    )
    ds_data = {"dateDerniereModification": "2025-01-01T12:00:00+02:00"}

    with patch(
        "gsl_demarches_simplifiees.importer.dossier.refresh_dossier_from_saved_data"
    ) as target_task:
        _save_dossier_data_and_refresh_dossier_and_projet_and_co(
            dossier, ds_data, async_refresh=False
        )
        target_task.assert_called_once_with(dossier)


def test_has_dossier_been_updated_on_ds():
    from gsl_demarches_simplifiees.importer.dossier import (
        _has_dossier_been_updated_on_ds,
    )

    dossier = DossierFactory.build(
        ds_date_derniere_modification=datetime.fromisoformat(
            "2024-10-16T10:09:33+02:00"
        )
    )

    # Case where DS date is more recent
    ds_data_newer = {"dateDerniereModification": "2025-01-01T12:00:00+02:00"}
    assert _has_dossier_been_updated_on_ds(dossier, ds_data_newer) is True

    # Case where DS date is older
    ds_data_older = {"dateDerniereModification": "2023-01-01T12:00:00+02:00"}
    assert _has_dossier_been_updated_on_ds(dossier, ds_data_older) is False
