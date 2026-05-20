import logging
from unittest.mock import patch

import pytest
from django.contrib import messages
from django.utils.timezone import datetime

from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsConnectionError, DsServiceException
from gsl_demarches_simplifiees.importer.dossier import (
    _commit_sync_cursors,
    _is_dossier_in_active_departement,
    _save_dossier_data_and_refresh_dossier_and_projet_and_co,
    import_one_dossier_from_ds,
    refresh_dossier_instructeurs,
    save_demarche_dossiers_from_ds,
    save_one_dossier_from_ds,
)
from gsl_demarches_simplifiees.models import Dossier, Profile
from gsl_demarches_simplifiees.tests.factories import (
    DemarcheFactory,
    DossierDataFactory,
    DossierFactory,
)


def _make_demarche_page(
    dossiers=None,
    pending_deleted=None,
    deleted=None,
    end_cursor=None,
    has_more_dossiers=False,
    pending_cursor=None,
    has_more_pending=False,
    deleted_cursor=None,
    has_more_deleted=False,
):
    """Helper to build a fetch_demarche_page return value for tests."""

    def _page(nodes, cursor=None, has_more=False):
        return {
            "pageInfo": {"hasNextPage": has_more, "endCursor": cursor},
            "nodes": nodes or [],
        }

    return {
        "dossiers": _page(dossiers, end_cursor, has_more_dossiers),
        "pendingDeletedDossiers": _page(
            pending_deleted, pending_cursor, has_more_pending
        ),
        "deletedDossiers": _page(deleted, deleted_cursor, has_more_deleted),
    }


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_calls_save_dossier_data_and_refresh_dossier_and_projet_and_co():
    demarche_number = 123
    DemarcheFactory(
        ds_number=demarche_number,
        raw_ds_data={"groupeInstructeurs": [{"id": "GROUPE-1", "instructeurs": []}]},
    )
    ds_dossiers = [
        {
            "id": "DOSS-1",
            "number": 20240001,
            "champs": [
                {
                    "label": "Département ou collectivité du demandeur",
                    "stringValue": "75 - Paris",
                }
            ],
        },
        {
            "id": "DOSS-2",
            "number": 20240002,
            "champs": [
                {
                    "label": "Département ou collectivité du demandeur",
                    "stringValue": "75 - Paris",
                }
            ],
        },
    ]

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.fetch_demarche_page",
        return_value=_make_demarche_page(dossiers=ds_dossiers),
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._get_active_departement_insee_codes",
            return_value=["75"],
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
    DemarcheFactory(
        ds_number=demarche_number,
        raw_ds_data={"groupeInstructeurs": [{"id": "GROUPE-1", "instructeurs": []}]},
    )
    dossier = DossierFactory(
        ds_id="DOSS-1",
        ds_number=20240001,
        ds_date_derniere_modification="2025-01-01T12:09:33+02:00",
    )
    DossierDataFactory(dossier=dossier, raw_data={"some_field": "some_value"})

    ds_dossiers = [
        {
            "id": "DOSS-1",
            "number": 20240001,
            "dateDerniereModification": "2025-01-01T12:09:33+02:00",
            "champs": [
                {
                    "label": "Département ou collectivité du demandeur",
                    "stringValue": "75 - Paris",
                }
            ],
        },
    ]

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.fetch_demarche_page",
        return_value=_make_demarche_page(dossiers=ds_dossiers),
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._get_active_departement_insee_codes",
            return_value=["75"],
        ):
            save_demarche_dossiers_from_ds(demarche_number)

            assert Dossier.objects.count() == 1
            dossier.refresh_from_db()

            assert dossier.ds_number == 20240001
            assert dossier.ds_data.raw_data == ds_dossiers[0]


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_with_one_empty_data(caplog):
    caplog.set_level(logging.INFO)
    demarche_number = 123
    DemarcheFactory(
        ds_number=demarche_number,
        raw_ds_data={"groupeInstructeurs": [{"id": "GROUPE-1", "instructeurs": []}]},
    )

    ds_dossiers = [
        {
            "id": "DOSS-1",
            "number": 20240001,
            "dateDerniereModification": "2025-01-01T12:09:33+02:00",
            "champs": [
                {
                    "label": "Département ou collectivité du demandeur",
                    "stringValue": "75 - Paris",
                }
            ],
        },
        None,
        {
            "id": "DOSS-2",
            "number": 20240002,
            "dateDerniereModification": "2025-01-01T12:09:33+02:00",
            "champs": [
                {
                    "label": "Département ou collectivité du demandeur",
                    "stringValue": "75 - Paris",
                }
            ],
        },
    ]

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.fetch_demarche_page",
        return_value=_make_demarche_page(dossiers=ds_dossiers),
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._get_active_departement_insee_codes",
            return_value=["75"],
        ):
            save_demarche_dossiers_from_ds(demarche_number)

            assert Dossier.objects.count() == 2
            assert "Dossier data is empty" in caplog.text


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_update_sync_cursor():
    demarche_number = 123
    expected_cursor = "abc123cursor=="
    demarche = DemarcheFactory(
        ds_number=demarche_number,
        sync_cursor="",
        raw_ds_data={"groupeInstructeurs": [{"id": "GROUPE-1", "instructeurs": []}]},
    )

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.fetch_demarche_page",
        return_value=_make_demarche_page(end_cursor=expected_cursor),
    ):
        save_demarche_dossiers_from_ds(demarche_number)

    demarche.refresh_from_db()
    assert demarche.sync_cursor == expected_cursor


def _ds_dossier(ds_id, number, departement_code="75"):
    return {
        "id": ds_id,
        "number": number,
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": f"{departement_code} - Département",
            }
        ],
    }


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_multipage_different_stream_lengths():
    """
    dossiers a 2 pages (3 dossiers au total), deletedDossiers a 1 page (1 dossier).
    Tous les dossiers des deux pages sont traités ; chaque curseur est sauvegardé
    indépendamment ; le 2e appel API n'inclut pas deleted (déjà épuisé).
    """
    demarche_number = 123
    demarche = DemarcheFactory(
        ds_number=demarche_number,
        sync_cursor="",
        raw_ds_data={"groupeInstructeurs": [{"id": "GROUPE-1", "instructeurs": []}]},
    )
    dossier_to_delete = DossierFactory(ds_number=20249999, is_active=True)

    page1 = _make_demarche_page(
        dossiers=[_ds_dossier("DOSS-1", 20240001), _ds_dossier("DOSS-2", 20240002)],
        deleted=[{"number": 20249999}],
        end_cursor="dossiers-cursor-1",
        has_more_dossiers=True,
        deleted_cursor="deleted-cursor-final",
        has_more_deleted=False,
    )
    page2 = _make_demarche_page(
        dossiers=[_ds_dossier("DOSS-3", 20240003)],
        end_cursor="dossiers-cursor-2",
        has_more_dossiers=False,
    )

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.fetch_demarche_page",
        side_effect=[page1, page2],
    ) as mock_fetch:
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._get_active_departement_insee_codes",
            return_value=["75"],
        ):
            with patch(
                "gsl_demarches_simplifiees.importer.dossier._save_dossier_data_and_refresh_dossier_and_projet_and_co"
            ):
                save_demarche_dossiers_from_ds(demarche_number)

    assert mock_fetch.call_count == 2
    first_call_kwargs = mock_fetch.call_args_list[0][1]
    assert first_call_kwargs["include_dossiers"] is True
    assert first_call_kwargs["include_deleted"] is True
    second_call_kwargs = mock_fetch.call_args_list[1][1]
    assert second_call_kwargs["include_dossiers"] is True
    assert second_call_kwargs["include_deleted"] is False

    # Les 3 dossiers (2 pages) ont bien été créés
    assert Dossier.objects.filter(ds_id="DOSS-1").exists()
    assert Dossier.objects.filter(ds_id="DOSS-2").exists()
    assert Dossier.objects.filter(ds_id="DOSS-3").exists()

    # Le dossier supprimé (1 page) a bien été désactivé
    dossier_to_delete.refresh_from_db()
    assert dossier_to_delete.is_active is False

    demarche.refresh_from_db()
    assert demarche.sync_cursor == "dossiers-cursor-2"
    assert demarche.deleted_cursor == "deleted-cursor-final"


@pytest.mark.django_db
def test_save_demarche_dossiers_from_ds_error_on_page_continues_but_skips_cursor():
    """Une erreur sur une page n'arrête pas la synchro mais empêche la sauvegarde du curseur."""
    demarche_number = 123
    initial_cursor = "old-cursor"
    demarche = DemarcheFactory(
        ds_number=demarche_number,
        sync_cursor=initial_cursor,
        updated_since="2025-01-01T00:00:00+00:00",
        raw_ds_data={"groupeInstructeurs": [{"id": "GROUPE-1", "instructeurs": []}]},
    )

    bad_dossier = {"id": "DOSS-BAD", "number": 99999, "champs": []}
    page1 = _make_demarche_page(
        dossiers=[bad_dossier],
        end_cursor="cursor-1",
        has_more_dossiers=True,
    )
    page2 = _make_demarche_page(end_cursor="cursor-2")

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.fetch_demarche_page",
        side_effect=[page1, page2],
    ) as mock_fetch:
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._create_or_update_dossier_from_ds_data",
            side_effect=Exception("boom"),
        ):
            save_demarche_dossiers_from_ds(demarche_number)

    assert mock_fetch.call_count == 2
    demarche.refresh_from_db()
    assert demarche.sync_cursor == initial_cursor


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

    # Incoming DN data only ships the groupe id; instructeurs are resolved locally
    ds_payload = {"groupeInstructeur": {"id": "GROUPE-1"}}
    groupe_index = {
        "GROUPE-1": [
            {"id": profile_b.ds_id, "email": profile_b.ds_email},
            {"id": "C-3", "email": "c@example.com"},
        ]
    }

    # First refresh: remove A, keep B, add C
    refresh_dossier_instructeurs(ds_payload, dossier, groupe_index=groupe_index)

    current_ids = set(dossier.ds_instructeurs.values_list("ds_id", flat=True))
    assert current_ids == {"B-2", "C-3"}

    # Ensure C profile was created with correct attributes
    c_profile = Profile.objects.get(ds_id="C-3")
    assert c_profile.ds_email == "c@example.com"

    # Second refresh with the same payload should be a no-op (no duplicates, same set)
    refresh_dossier_instructeurs(ds_payload, dossier, groupe_index=groupe_index)
    current_ids_again = set(dossier.ds_instructeurs.values_list("ds_id", flat=True))
    assert current_ids_again == {"B-2", "C-3"}
    assert dossier.ds_instructeurs.count() == 2


@pytest.mark.django_db
def test_refresh_dossier_instructeurs_builds_index_from_demarche_raw_data():
    """When no groupe_index is passed, it is rebuilt from Demarche.raw_ds_data."""
    demarche = DemarcheFactory(
        raw_ds_data={
            "groupeInstructeurs": [
                {
                    "id": "GROUPE-1",
                    "instructeurs": [
                        {"id": "A-1", "email": "a@example.com"},
                        {"id": "B-2", "email": "b@example.com"},
                    ],
                },
                {
                    "id": "GROUPE-2",
                    "instructeurs": [
                        {"id": "Z-9", "email": "z@example.com"},
                    ],
                },
            ]
        }
    )
    dossier = DossierFactory(ds_demarche=demarche)

    ds_payload = {"groupeInstructeur": {"id": "GROUPE-1"}}
    refresh_dossier_instructeurs(ds_payload, dossier)

    current_ids = set(dossier.ds_instructeurs.values_list("ds_id", flat=True))
    assert current_ids == {"A-1", "B-2"}


@pytest.mark.django_db
def test_refresh_dossier_instructeurs_unknown_groupe_id_logs_warning(caplog):
    """If the dossier's groupe id is unknown even after refreshing the demarche,
    log a warning and leave instructeurs untouched."""
    demarche = DemarcheFactory(
        raw_ds_data={
            "groupeInstructeurs": [
                {
                    "id": "GROUPE-1",
                    "instructeurs": [{"id": "A-1", "email": "a@example.com"}],
                },
            ]
        }
    )
    dossier = DossierFactory(ds_demarche=demarche)
    profile = Profile.objects.create(ds_id="EXISTING", ds_email="x@example.com")
    dossier.ds_instructeurs.add(profile)

    ds_payload = {"groupeInstructeur": {"id": "GROUPE-UNKNOWN"}}

    # save_demarche_from_ds is stubbed to do nothing, so the id stays unknown.
    with patch(
        "gsl_demarches_simplifiees.importer.demarche.save_demarche_from_ds"
    ) as mock_save_demarche:
        with caplog.at_level(logging.WARNING):
            refresh_dossier_instructeurs(ds_payload, dossier, groupe_index={})

    mock_save_demarche.assert_called_once_with(demarche.ds_number)
    assert "Unknown groupeInstructeur id" in caplog.text
    # Untouched
    assert set(dossier.ds_instructeurs.values_list("ds_id", flat=True)) == {"EXISTING"}


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

    # Case where DN date is more recent
    ds_data_newer = {"dateDerniereModification": "2025-01-01T12:00:00+02:00"}
    assert _has_dossier_been_updated_on_ds(dossier, ds_data_newer) is True

    # Case where DN date is older
    ds_data_older = {"dateDerniereModification": "2023-01-01T12:00:00+02:00"}
    assert _has_dossier_been_updated_on_ds(dossier, ds_data_older) is False


# test _is_dossier_in_active_departement


def test_is_dossier_in_active_departement_department_found_and_in_active_list():
    """Test when department field is found and code is in active departments."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "75 - Paris",
            }
        ]
    }
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is True
    assert label == "75 - Paris"


def test_is_dossier_in_active_departement_department_found_but_not_in_active_list():
    """Test when department field is found but code is NOT in active departments."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "75 - Paris",
            }
        ]
    }
    departements_actifs = ["13", "69", "92"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is False
    assert label == "75 - Paris"


def test_is_dossier_in_active_departement_empty_value():
    """Test when department field is found but value is empty."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "",
            }
        ]
    }
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is False
    assert label == ""


def test_is_dossier_in_active_departement_whitespace_only_value():
    """Test when department field has only whitespace."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "   ",
            }
        ]
    }
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is False
    assert label == ""


def test_is_dossier_in_active_departement_field_not_found():
    """Test when department field is not found in champs."""
    raw_data = {
        "champs": [
            {"label": "Autre champ", "stringValue": "75 - Paris"},
        ]
    }
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is False
    assert label == "inconnu"


def test_is_dossier_in_active_departement_no_champs_key():
    """Test when champs key is missing from raw_data."""
    raw_data = {}
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is False
    assert label == "inconnu"


def test_is_dossier_in_active_departement_empty_champs():
    """Test when champs is an empty list."""
    raw_data = {"champs": []}
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is False
    assert label == "inconnu"


def test_is_dossier_in_active_departement_with_whitespace_in_code():
    """Test when department code has whitespace that should be stripped."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "  75  - Paris",
            }
        ]
    }
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is True
    assert label == "75  - Paris"


def test_is_dossier_in_active_departement_with_different_format():
    """Test with different format variations."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "13- Bouches-du-Rhône",
            }
        ]
    }
    departements_actifs = ["13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is True
    assert label == "13- Bouches-du-Rhône"


def test_is_dossier_in_active_departement_with_list_of_strings():
    """Test that it works with list of strings for active departments."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "69 - Rhône",
            }
        ]
    }
    departements_actifs = ["69", "75"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is True
    assert label == "69 - Rhône"


def test_is_dossier_in_active_departement_with_set():
    """Test that it works with a set for active departments."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": "92 - Hauts-de-Seine",
            }
        ]
    }
    departements_actifs = {"92", "75", "13"}
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is True
    assert label == "92 - Hauts-de-Seine"


def test_is_dossier_in_active_departement_no_stringValue_key():
    """Test when stringValue key is missing from the champ."""
    raw_data = {
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
            }
        ]
    }
    departements_actifs = ["75", "13", "69"]
    is_active, label = _is_dossier_in_active_departement(raw_data, departements_actifs)
    assert is_active is False
    assert label == ""


@pytest.mark.django_db
def test_archived_dossier_in_ds_stream_deactivates_existing_dossier():
    demarche_number = 123
    DemarcheFactory(
        ds_number=demarche_number,
        raw_ds_data={"groupeInstructeurs": [{"id": "GROUPE-1", "instructeurs": []}]},
    )
    dossier = DossierFactory(ds_id="DOSS-1", ds_number=20240001, is_active=True)
    ds_dossiers = [
        {
            "id": "DOSS-1",
            "number": 20240001,
            "archived": True,
            "annotations": [],
            "demarche": {"revision": {"id": "REV-1"}},
            "champs": [
                {
                    "id": "CHAMP-DEPT",
                    "label": "Département ou collectivité du demandeur",
                    "stringValue": "75 - Paris",
                }
            ],
        }
    ]

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.fetch_demarche_page",
        return_value=_make_demarche_page(dossiers=ds_dossiers),
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._get_active_departement_insee_codes",
            return_value=["75"],
        ):
            save_demarche_dossiers_from_ds(demarche_number)

    dossier.refresh_from_db()
    assert dossier.is_active is False
    assert dossier.raison_desactivation == Dossier.RAISON_DESACTIVATION_ARCHIVE


# tests import_one_dossier_from_ds


def _make_dossier_data(dossier_number, demarche_number, departement_code="75"):
    return {
        "id": f"DOSS-{dossier_number}",
        "number": dossier_number,
        "demarche": {"number": demarche_number},
        "champs": [
            {
                "label": "Département ou collectivité du demandeur",
                "stringValue": f"{departement_code} - Département",
            }
        ],
    }


@pytest.mark.parametrize("exception_class", [DsServiceException, DsConnectionError])
def test_import_one_dossier_from_ds_erreur_dn(exception_class):
    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_one_dossier",
        side_effect=exception_class,
    ):
        level, message = import_one_dossier_from_ds(20240001)

    assert level == messages.WARNING
    assert "20240001" in message
    if exception_class == DsConnectionError:
        assert (
            "Erreur : Nous n'arrivons pas à nous connecter à Démarche Numérique."
            in message
        )


@pytest.mark.django_db
def test_import_one_dossier_from_ds_demarche_absente(caplog):
    caplog.set_level(logging.INFO)
    dossier_number = 20240001
    dossier_data = _make_dossier_data(dossier_number, demarche_number=9999)

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_one_dossier",
        return_value=dossier_data,
    ):
        level, message = import_one_dossier_from_ds(dossier_number)

    assert Dossier.objects.count() == 0
    assert level == messages.WARNING
    assert "9999" in message
    assert "Démarche absente de Turgot" in caplog.text


@pytest.mark.django_db
def test_import_one_dossier_from_ds_dossier_deja_existant(caplog):
    caplog.set_level(logging.INFO)
    demarche = DemarcheFactory()
    existing_dossier = DossierFactory(ds_number=20240001, ds_demarche=demarche)
    dossier_data = _make_dossier_data(20240001, demarche.ds_number)

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_one_dossier",
        return_value=dossier_data,
    ):
        level, message = import_one_dossier_from_ds(20240001)

    assert Dossier.objects.count() == 1
    assert Dossier.objects.filter(pk=existing_dossier.pk).exists()
    assert level == messages.WARNING
    assert "20240001" in message
    assert "Dossier déjà présent dans Turgot" in caplog.text


@pytest.mark.django_db
def test_import_one_dossier_from_ds_departement_inactif(caplog):
    caplog.set_level(logging.INFO)
    demarche = DemarcheFactory()
    dossier_number = 20240001
    dossier_data = _make_dossier_data(
        dossier_number, demarche.ds_number, departement_code="99"
    )

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_one_dossier",
        return_value=dossier_data,
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._get_active_departement_insee_codes",
            return_value=["75"],
        ):
            level, message = import_one_dossier_from_ds(dossier_number)

    assert Dossier.objects.count() == 0
    assert level == messages.WARNING
    assert "99" in message
    assert "Dossier dans un département inactif" in caplog.text


@pytest.mark.django_db
def test_import_one_dossier_from_ds_cree_le_dossier():
    demarche = DemarcheFactory()
    dossier_number = 20240001
    dossier_data = _make_dossier_data(dossier_number, demarche.ds_number)

    with patch(
        "gsl_demarches_simplifiees.ds_client.DsClient.get_one_dossier",
        return_value=dossier_data,
    ):
        with patch(
            "gsl_demarches_simplifiees.importer.dossier._get_active_departement_insee_codes",
            return_value=["75"],
        ):
            with patch(
                "gsl_demarches_simplifiees.importer.dossier._save_dossier_data_and_refresh_dossier_and_projet_and_co"
            ) as mock_refresh:
                level, message = import_one_dossier_from_ds(dossier_number)

    assert Dossier.objects.filter(ds_number=dossier_number).exists()
    assert level == messages.SUCCESS
    assert "20240001" in message
    mock_refresh.assert_called_once()


# tests _commit_sync_cursors

_API_UPDATED_SINCE = datetime.fromisoformat("2025-06-01T00:00:00+00:00")


@pytest.mark.django_db
def test_commit_sync_cursors_no_errors_updates_all_cursors():
    demarche = DemarcheFactory(
        sync_cursor="old-d",
        pending_deleted_cursor="old-p",
        deleted_cursor="old-del",
    )

    _commit_sync_cursors(
        demarche,
        False,
        dossiers_cursor="new-d",
        dossiers_any_error=False,
        pending_deleted_cursor="new-p",
        pending_any_error=False,
        deleted_cursor="new-del",
        deleted_any_error=False,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.sync_cursor == "new-d"
    assert demarche.pending_deleted_cursor == "new-p"
    assert demarche.deleted_cursor == "new-del"
    assert demarche.updated_since == _API_UPDATED_SINCE


@pytest.mark.django_db
def test_commit_sync_cursors_updated_since_always_saved():
    demarche = DemarcheFactory(updated_since=None)

    _commit_sync_cursors(
        demarche,
        True,
        dossiers_cursor=None,
        dossiers_any_error=True,
        pending_deleted_cursor=None,
        pending_any_error=True,
        deleted_cursor=None,
        deleted_any_error=True,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.updated_since == _API_UPDATED_SINCE


# has_date_changed=False (sync suivante) : erreur → on garde l'ancien curseur


@pytest.mark.django_db
def test_commit_sync_cursors_dossiers_error_keeps_sync_cursor():
    demarche = DemarcheFactory(sync_cursor="old-d")

    _commit_sync_cursors(
        demarche,
        False,
        dossiers_cursor="new-d",
        dossiers_any_error=True,
        pending_deleted_cursor="new-p",
        pending_any_error=False,
        deleted_cursor="new-del",
        deleted_any_error=False,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.sync_cursor == "old-d"
    assert demarche.pending_deleted_cursor == "new-p"
    assert demarche.deleted_cursor == "new-del"


@pytest.mark.django_db
def test_commit_sync_cursors_pending_error_keeps_pending_cursor():
    demarche = DemarcheFactory(pending_deleted_cursor="old-p")

    _commit_sync_cursors(
        demarche,
        False,
        dossiers_cursor="new-d",
        dossiers_any_error=False,
        pending_deleted_cursor="new-p",
        pending_any_error=True,
        deleted_cursor="new-del",
        deleted_any_error=False,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.sync_cursor == "new-d"
    assert demarche.pending_deleted_cursor == "old-p"
    assert demarche.deleted_cursor == "new-del"


@pytest.mark.django_db
def test_commit_sync_cursors_deleted_error_keeps_deleted_cursor():
    demarche = DemarcheFactory(deleted_cursor="old-del")

    _commit_sync_cursors(
        demarche,
        False,
        dossiers_cursor="new-d",
        dossiers_any_error=False,
        pending_deleted_cursor="new-p",
        pending_any_error=False,
        deleted_cursor="new-del",
        deleted_any_error=True,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.sync_cursor == "new-d"
    assert demarche.pending_deleted_cursor == "new-p"
    assert demarche.deleted_cursor == "old-del"


# has_date_changed=True (première sync) : erreur → on remet le curseur à None


@pytest.mark.django_db
def test_commit_sync_cursors_dossiers_error_with_date_changed_resets_cursor():
    demarche = DemarcheFactory(sync_cursor="old-d")

    _commit_sync_cursors(
        demarche,
        True,
        dossiers_cursor="new-d",
        dossiers_any_error=True,
        pending_deleted_cursor="new-p",
        pending_any_error=False,
        deleted_cursor="new-del",
        deleted_any_error=False,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.sync_cursor == ""  # remis à zéro
    assert demarche.pending_deleted_cursor == "new-p"
    assert demarche.deleted_cursor == "new-del"


@pytest.mark.django_db
def test_commit_sync_cursors_pending_error_with_date_changed_resets_cursor():
    demarche = DemarcheFactory(pending_deleted_cursor="old-p")

    _commit_sync_cursors(
        demarche,
        True,
        dossiers_cursor="new-d",
        dossiers_any_error=False,
        pending_deleted_cursor="new-p",
        pending_any_error=True,
        deleted_cursor="new-del",
        deleted_any_error=False,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.sync_cursor == "new-d"
    assert demarche.pending_deleted_cursor == ""  # remis à zéro
    assert demarche.deleted_cursor == "new-del"


@pytest.mark.django_db
def test_commit_sync_cursors_deleted_error_with_date_changed_resets_cursor():
    demarche = DemarcheFactory(deleted_cursor="old-del")

    _commit_sync_cursors(
        demarche,
        True,
        dossiers_cursor="new-d",
        dossiers_any_error=False,
        pending_deleted_cursor="new-p",
        pending_any_error=False,
        deleted_cursor="new-del",
        deleted_any_error=True,
        api_updated_since=_API_UPDATED_SINCE,
    )

    demarche.refresh_from_db()
    assert demarche.sync_cursor == "new-d"
    assert demarche.pending_deleted_cursor == "new-p"
    assert demarche.deleted_cursor == ""  # remis à zéro
