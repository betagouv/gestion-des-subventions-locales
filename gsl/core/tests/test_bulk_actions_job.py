import pytest
from django.db import IntegrityError

from gsl.core.models import BulkActionsJob
from gsl.core.tests.factories import BulkActionsJobFactory

pytestmark = pytest.mark.django_db


def test_new_job_defaults():
    job = BulkActionsJobFactory(object_ids=[1, 2, 3])

    assert job.status == BulkActionsJob.Status.PENDING
    assert job.is_unfinished
    assert job.total == 3
    assert job.processed == 0
    assert job.succeeded_count == 0
    assert job.report == []
    assert job.params == {}
    assert job.errors_summary() == {}


@pytest.mark.parametrize(
    ("status", "expected_is_unfinished"),
    (
        (BulkActionsJob.Status.PENDING, True),
        (BulkActionsJob.Status.RUNNING, True),
        (BulkActionsJob.Status.DONE, False),
    ),
)
def test_is_unfinished(status, expected_is_unfinished):
    job = BulkActionsJobFactory(status=status)

    assert job.is_unfinished is expected_is_unfinished


def test_params_keep_action_specific_data():
    params = {"motivation": "Bravo", "dotation": "DETR", "nested": {"ids": [1, 2]}}
    job = BulkActionsJobFactory(params=params)

    job.refresh_from_db()
    assert job.params == params


def test_record_success_increments_processed():
    job = BulkActionsJobFactory(object_ids=[1, 2])

    job.record_success()
    job.record_success()

    assert job.processed == 2
    assert job.succeeded_count == 2
    job.refresh_from_db()
    assert job.processed == 2


def test_record_success_does_not_lose_increments_from_a_stale_instance():
    job = BulkActionsJobFactory(object_ids=[1, 2])
    stale_job = BulkActionsJob.objects.get(pk=job.pk)

    job.record_success()
    stale_job.record_success()

    job.refresh_from_db()
    assert job.processed == 2


def test_record_error_stores_the_error_and_increments_processed():
    job = BulkActionsJobFactory(object_ids=[42])

    job.record_error(42, "123456", "Document signé manquant")

    expected = [
        {"object_id": 42, "label": "123456", "message": "Document signé manquant"}
    ]
    assert job.report == expected
    assert job.processed == 1
    assert job.succeeded_count == 0
    job.refresh_from_db()
    assert job.report == expected
    assert job.processed == 1


def test_succeeded_count_excludes_errors():
    job = BulkActionsJobFactory(object_ids=[1, 2, 3])

    job.record_success()
    job.record_error(2, "222", "Erreur DN")
    job.record_error(3, "333", "Erreur DN")

    assert job.processed == 3
    assert job.succeeded_count == 1


def test_errors_summary_groups_labels_by_message():
    job = BulkActionsJobFactory(object_ids=[1, 2, 3, 4])

    job.record_error(1, "111", "Erreur DN")
    job.record_error(2, "222", "Document signé manquant")
    job.record_error(3, "333", "Erreur DN")
    job.record_error(4, "444", "Document signé manquant")

    assert job.errors_summary() == {
        "Erreur DN": ["111", "333"],
        "Document signé manquant": ["222", "444"],
    }
    assert list(job.errors_summary()) == ["Erreur DN", "Document signé manquant"]


@pytest.mark.parametrize(
    "existing_status, new_status",
    (
        (BulkActionsJob.Status.RUNNING, BulkActionsJob.Status.RUNNING),
        (BulkActionsJob.Status.RUNNING, BulkActionsJob.Status.PENDING),
        (BulkActionsJob.Status.PENDING, BulkActionsJob.Status.PENDING),
        (BulkActionsJob.Status.PENDING, BulkActionsJob.Status.RUNNING),
    ),
)
def test_two_active_jobs_cannot_share_a_lock_key(existing_status, new_status):
    BulkActionsJobFactory(lock_key="simulation:1", status=existing_status)

    with pytest.raises(IntegrityError):
        BulkActionsJobFactory(lock_key="simulation:1", status=new_status)


@pytest.mark.parametrize(
    "new_status",
    (
        BulkActionsJob.Status.PENDING,
        BulkActionsJob.Status.RUNNING,
        BulkActionsJob.Status.DONE,
    ),
)
def test_a_done_job_does_not_hold_its_lock_key(new_status):
    BulkActionsJobFactory(lock_key="simulation:1", status=BulkActionsJob.Status.DONE)

    BulkActionsJobFactory(lock_key="simulation:1", status=new_status)

    assert BulkActionsJob.objects.filter(lock_key="simulation:1").count() == 2


def test_jobs_without_lock_key_can_run_concurrently():
    BulkActionsJobFactory(status=BulkActionsJob.Status.RUNNING)
    BulkActionsJobFactory(status=BulkActionsJob.Status.RUNNING)

    assert BulkActionsJob.objects.count() == 2


def test_unfinished_excludes_done_jobs():
    pending = BulkActionsJobFactory(status=BulkActionsJob.Status.PENDING)
    running = BulkActionsJobFactory(status=BulkActionsJob.Status.RUNNING)
    BulkActionsJobFactory(status=BulkActionsJob.Status.DONE)

    assert set(BulkActionsJob.objects.unfinished()) == {pending, running}


def test_active_jobs_of_different_actions_can_share_a_lock_key():
    BulkActionsJobFactory(action="action_a", lock_key="simulation:1")
    BulkActionsJobFactory(action="action_b", lock_key="simulation:1")

    assert BulkActionsJob.objects.filter(lock_key="simulation:1").count() == 2
