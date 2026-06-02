from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from gsl_demarches_simplifiees.locks import demarche_sync_lock
from gsl_demarches_simplifiees.tasks import (
    task_init_demarche_sync,
    task_save_demarche_dossiers_from_ds,
)
from gsl_demarches_simplifiees.tests.factories import DemarcheFactory


@contextmanager
def _fake_lock(acquired):
    """Remplace demarche_sync_lock en yieldant la valeur voulue."""
    yield acquired


# --- task_save_demarche_dossiers_from_ds -----------------------------------


@patch("gsl_demarches_simplifiees.tasks.save_demarche_dossiers_from_ds")
@patch("gsl_demarches_simplifiees.tasks.demarche_sync_lock")
def test_save_dossiers_skips_when_lock_held(mock_lock, mock_save):
    mock_lock.return_value = _fake_lock(False)

    result = task_save_demarche_dossiers_from_ds(123)

    assert result is None
    mock_save.assert_not_called()


@patch("gsl_demarches_simplifiees.tasks.save_demarche_dossiers_from_ds")
@patch("gsl_demarches_simplifiees.tasks.demarche_sync_lock")
def test_save_dossiers_runs_when_lock_free(mock_lock, mock_save):
    mock_lock.return_value = _fake_lock(True)
    mock_save.return_value = "done"

    result = task_save_demarche_dossiers_from_ds(123)

    assert result == "done"
    mock_save.assert_called_once_with(123)
    mock_lock.assert_called_once_with(123, timeout=settings.DS_SYNC_LOCK_TIMEOUT)


# --- task_init_demarche_sync -----------------------------------------------


@pytest.mark.django_db
@patch("gsl_demarches_simplifiees.tasks.save_demarche_dossiers_from_ds")
@patch("gsl_demarches_simplifiees.tasks.demarche_sync_lock")
def test_init_sync_skips_when_lock_held(mock_lock, mock_save):
    mock_lock.return_value = _fake_lock(False)
    demarche = DemarcheFactory(
        sync_cursor="cursor-1",
        pending_deleted_cursor="cursor-2",
        deleted_cursor="cursor-3",
    )

    result = task_init_demarche_sync(demarche.ds_number, "2026-01-01T00:00:00Z")

    assert result is None
    mock_save.assert_not_called()
    demarche.refresh_from_db()
    assert demarche.sync_cursor == "cursor-1"
    assert demarche.pending_deleted_cursor == "cursor-2"
    assert demarche.deleted_cursor == "cursor-3"


@pytest.mark.django_db
@patch("gsl_demarches_simplifiees.tasks.save_demarche_dossiers_from_ds")
@patch("gsl_demarches_simplifiees.tasks.demarche_sync_lock")
def test_init_sync_resets_cursors_when_lock_free(mock_lock, mock_save):
    mock_lock.return_value = _fake_lock(True)
    mock_save.return_value = "done"
    demarche = DemarcheFactory(
        sync_cursor="cursor-1",
        pending_deleted_cursor="cursor-2",
        deleted_cursor="cursor-3",
    )

    result = task_init_demarche_sync(demarche.ds_number, "2026-01-01T00:00:00Z")

    assert result == "done"
    mock_save.assert_called_once_with(demarche.ds_number)
    mock_lock.assert_called_once_with(
        demarche.ds_number, timeout=settings.DS_INIT_SYNC_LOCK_TIMEOUT
    )
    demarche.refresh_from_db()
    assert demarche.sync_cursor == ""
    assert demarche.pending_deleted_cursor == ""
    assert demarche.deleted_cursor == ""


# --- demarche_sync_lock context manager ------------------------------------


@patch("gsl_demarches_simplifiees.locks.redis.Redis.from_url")
def test_lock_yields_true_and_releases_when_acquired(mock_from_url):
    lock = MagicMock()
    lock.acquire.return_value = True
    client = MagicMock()
    client.lock.return_value = lock
    mock_from_url.return_value = client

    with demarche_sync_lock(42, timeout=123) as acquired:
        assert acquired is True

    client.lock.assert_called_once_with("ds:demarche-sync:42", timeout=123)
    lock.acquire.assert_called_once_with(blocking=False)
    lock.release.assert_called_once()


@patch("gsl_demarches_simplifiees.locks.redis.Redis.from_url")
def test_lock_yields_false_and_does_not_release_when_held(mock_from_url):
    lock = MagicMock()
    lock.acquire.return_value = False
    client = MagicMock()
    client.lock.return_value = lock
    mock_from_url.return_value = client

    with demarche_sync_lock(42, timeout=123) as acquired:
        assert acquired is False

    lock.release.assert_not_called()
