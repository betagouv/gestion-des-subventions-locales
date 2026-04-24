from decimal import Decimal
from unittest import mock

import pytest

from gsl_core.tests.factories import (
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import PROJET_STATUS_ACCEPTED
from gsl_simulation.models import BulkStatusJob, SimulationProjet
from gsl_simulation.tasks import run_bulk_status_job
from gsl_simulation.tests.factories import SimulationFactory, make_detr_simu_projet

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre):
    return CollegueWithDSProfileFactory(perimetre=perimetre)


@pytest.fixture
def simulation(perimetre):
    enveloppe = DetrEnveloppeFactory(perimetre=perimetre, annee=2025, montant=1_000_000)
    return SimulationFactory(enveloppe=enveloppe)


def _make_simu_projet(perimetre, simulation, **kwargs):
    kwargs.setdefault("montant", Decimal("1000"))
    kwargs.setdefault("assiette", Decimal("10000"))
    return make_detr_simu_projet(perimetre, simulation, **kwargs)


def _make_job(simulation, collegue, simulation_projets, target_status):
    ids = [sp.pk for sp in simulation_projets]
    return BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=target_status,
        simulation_projet_ids=ids,
    )


def test_run_bulk_status_job_to_provisional_accepted_updates_all_rows(
    collegue, perimetre, simulation
):
    sp1 = _make_simu_projet(perimetre, simulation)
    sp2 = _make_simu_projet(perimetre, simulation)
    job = _make_job(
        simulation, collegue, [sp1, sp2], SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    )

    run_bulk_status_job(str(job.pk))

    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    assert job.processed == 2
    assert job.errors == []
    for sp in (sp1, sp2):
        sp.refresh_from_db()
        assert sp.status == SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED


def test_run_bulk_status_job_to_accepted_fires_ds_mutation_per_row(
    collegue, perimetre, simulation
):
    sp = _make_simu_projet(perimetre, simulation)
    job = _make_job(simulation, collegue, [sp], SimulationProjet.STATUS_ACCEPTED)

    with mock.patch(
        "gsl_projet.models.DsService.update_ds_annotations_for_one_dotation"
    ) as ds_mock:
        run_bulk_status_job(str(job.pk))

    assert ds_mock.called
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_ACCEPTED
    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    assert job.errors == []


def test_run_bulk_status_job_continues_when_one_row_fails_ds(
    collegue, perimetre, simulation
):
    sp_ok_1 = _make_simu_projet(perimetre, simulation)
    sp_fails = _make_simu_projet(perimetre, simulation)
    sp_ok_2 = _make_simu_projet(perimetre, simulation)
    job = _make_job(
        simulation,
        collegue,
        [sp_ok_1, sp_fails, sp_ok_2],
        SimulationProjet.STATUS_ACCEPTED,
    )

    call_ids = []

    def side_effect(*args, **kwargs):
        dossier = kwargs.get("dossier") or args[0]
        call_ids.append(dossier.id)
        if dossier.id == sp_fails.projet.dossier_ds.id:
            raise DsServiceException("Échec DN simulé")
        return None

    with mock.patch(
        "gsl_projet.models.DsService.update_ds_annotations_for_one_dotation",
        side_effect=side_effect,
    ):
        run_bulk_status_job(str(job.pk))

    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    assert job.processed == 3
    assert len(job.errors) == 1
    error = job.errors[0]
    assert error["simulation_projet_id"] == sp_fails.pk
    assert "Échec DN simulé" in error["message"]

    sp_ok_1.refresh_from_db()
    sp_fails.refresh_from_db()
    sp_ok_2.refresh_from_db()
    assert sp_ok_1.status == SimulationProjet.STATUS_ACCEPTED
    assert sp_ok_2.status == SimulationProjet.STATUS_ACCEPTED
    # Failing row is unchanged (local update was rolled back by accept()'s atomic block).
    assert sp_fails.status == SimulationProjet.STATUS_PROCESSING


def test_run_bulk_status_job_records_validation_error_for_missing_assiette(
    collegue, perimetre, simulation
):
    sp = _make_simu_projet(perimetre, simulation, assiette=None)
    job = _make_job(simulation, collegue, [sp], SimulationProjet.STATUS_ACCEPTED)

    with mock.patch(
        "gsl_projet.models.DsService.update_ds_annotations_for_one_dotation"
    ) as ds_mock:
        run_bulk_status_job(str(job.pk))

    ds_mock.assert_not_called()
    job.refresh_from_db()
    assert job.processed == 1
    assert len(job.errors) == 1
    assert "assiette" in job.errors[0]["message"].lower()
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROCESSING


def test_run_bulk_status_job_from_accepted_back_to_processing(
    collegue, perimetre, simulation
):
    sp = _make_simu_projet(
        perimetre,
        simulation,
        dotation_status=PROJET_STATUS_ACCEPTED,
        simu_status=SimulationProjet.STATUS_ACCEPTED,
    )
    job = _make_job(simulation, collegue, [sp], SimulationProjet.STATUS_PROCESSING)

    with mock.patch(
        "gsl_projet.models.DsService.update_ds_annotations_for_one_dotation"
    ) as ds_mock:
        run_bulk_status_job(str(job.pk))

    assert ds_mock.called
    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROCESSING
    job.refresh_from_db()
    assert job.errors == []


def test_run_bulk_status_job_lets_unexpected_exception_propagate(
    collegue, perimetre, simulation
):
    sp1 = _make_simu_projet(perimetre, simulation)
    sp2 = _make_simu_projet(perimetre, simulation)
    sp3 = _make_simu_projet(perimetre, simulation)
    job = _make_job(
        simulation,
        collegue,
        [sp1, sp2, sp3],
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
    )

    from gsl_simulation.forms import SimulationProjetStatusForm as _Form

    original_save = _Form.save

    def side_effect(self, *args, **kwargs):
        if self.instance.pk == sp2.pk:
            raise RuntimeError("boom")
        return original_save(self, *args, **kwargs)

    with mock.patch(
        "gsl_simulation.tasks.SimulationProjetStatusForm.save",
        autospec=True,
        side_effect=side_effect,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            run_bulk_status_job(str(job.pk))

    job.refresh_from_db()
    # The outer finally marks the job DONE with the crash sentinel so the UI
    # stops polling; the exception still propagates so Celery/Sentry see it.
    assert job.status == BulkStatusJob.STATUS_DONE
    assert len(job.errors) == 1
    assert "interrompu" in job.errors[0]["message"].lower()

    sp1.refresh_from_db()
    sp2.refresh_from_db()
    sp3.refresh_from_db()
    # sp1 was processed before the crash, sp2 crashed, sp3 was never reached.
    assert sp1.status == SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    assert sp2.status == SimulationProjet.STATUS_PROCESSING
    assert sp3.status == SimulationProjet.STATUS_PROCESSING


def test_run_bulk_status_job_preserves_recorded_errors_when_crashing(
    collegue, perimetre, simulation
):
    sp1 = _make_simu_projet(perimetre, simulation)
    sp2 = _make_simu_projet(perimetre, simulation)
    sp3 = _make_simu_projet(perimetre, simulation)
    job = _make_job(
        simulation,
        collegue,
        [sp1, sp2, sp3],
        SimulationProjet.STATUS_ACCEPTED,
    )

    def ds_side_effect(*args, **kwargs):
        dossier = kwargs.get("dossier") or args[0]
        if dossier.id == sp2.projet.dossier_ds.id:
            raise DsServiceException("Échec DN simulé")
        return None

    from gsl_simulation.forms import SimulationProjetStatusForm as _Form

    original_save = _Form.save

    def save_side_effect(self, *args, **kwargs):
        if self.instance.pk == sp3.pk:
            raise RuntimeError("boom")
        return original_save(self, *args, **kwargs)

    with (
        mock.patch(
            "gsl_projet.models.DsService.update_ds_annotations_for_one_dotation",
            side_effect=ds_side_effect,
        ),
        mock.patch(
            "gsl_simulation.tasks.SimulationProjetStatusForm.save",
            autospec=True,
            side_effect=save_side_effect,
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        run_bulk_status_job(str(job.pk))

    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    # Both sp2's DN failure (recorded during the loop) and the sp3 crash sentinel
    # should be persisted — the pre-fix behaviour lost sp2's error entirely.
    assert len(job.errors) == 2
    recorded = job.errors[0]
    sentinel = job.errors[1]
    assert recorded["simulation_projet_id"] == sp2.pk
    assert "Échec DN simulé" in recorded["message"]
    assert sentinel["simulation_projet_id"] is None
    assert "interrompu" in sentinel["message"].lower()


def test_run_bulk_status_job_records_transition_not_allowed_per_row(
    collegue, perimetre, simulation
):
    from django_fsm import TransitionNotAllowed

    sp_ok = _make_simu_projet(perimetre, simulation)
    sp_fails = _make_simu_projet(perimetre, simulation)
    job = _make_job(
        simulation,
        collegue,
        [sp_ok, sp_fails],
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
    )

    from gsl_simulation.forms import SimulationProjetStatusForm as _Form

    original_save = _Form.save

    def side_effect(self, *args, **kwargs):
        if self.instance.pk == sp_fails.pk:
            raise TransitionNotAllowed("nope")
        return original_save(self, *args, **kwargs)

    with mock.patch(
        "gsl_simulation.tasks.SimulationProjetStatusForm.save",
        autospec=True,
        side_effect=side_effect,
    ):
        run_bulk_status_job(str(job.pk))

    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    assert job.processed == 2
    assert len(job.errors) == 1
    assert job.errors[0]["simulation_projet_id"] == sp_fails.pk
    assert "transition" in job.errors[0]["message"].lower()


def test_run_bulk_status_job_records_validation_error_per_row(
    collegue, perimetre, simulation
):
    from django.core.exceptions import ValidationError as DjValidationError

    sp_ok = _make_simu_projet(perimetre, simulation)
    sp_fails = _make_simu_projet(perimetre, simulation)
    job = _make_job(
        simulation,
        collegue,
        [sp_ok, sp_fails],
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
    )

    from gsl_simulation.forms import SimulationProjetStatusForm as _Form

    original_save = _Form.save

    def side_effect(self, *args, **kwargs):
        if self.instance.pk == sp_fails.pk:
            raise DjValidationError("Dotation incohérente avec l'enveloppe.")
        return original_save(self, *args, **kwargs)

    with mock.patch(
        "gsl_simulation.tasks.SimulationProjetStatusForm.save",
        autospec=True,
        side_effect=side_effect,
    ):
        run_bulk_status_job(str(job.pk))

    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    assert job.processed == 2
    assert len(job.errors) == 1
    assert job.errors[0]["simulation_projet_id"] == sp_fails.pk
    assert "Dotation incohérente" in job.errors[0]["message"]


def test_run_bulk_status_job_marks_done_when_loop_setup_fails(
    collegue, perimetre, simulation
):
    sp = _make_simu_projet(perimetre, simulation)
    job = _make_job(
        simulation, collegue, [sp], SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    )

    with mock.patch(
        "gsl_simulation.tasks.SimulationProjet.objects.filter",
        side_effect=RuntimeError("db boom"),
    ):
        with pytest.raises(RuntimeError, match="db boom"):
            run_bulk_status_job(str(job.pk))

    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    assert len(job.errors) == 1
    assert "interrompu" in job.errors[0]["message"].lower()


def test_run_bulk_status_job_records_error_for_notified_projects(
    collegue, perimetre, simulation
):
    sp = _make_simu_projet(perimetre, simulation)
    sp.projet.notified_at = "2025-01-01T00:00:00Z"
    sp.projet.save()
    job = _make_job(
        simulation, collegue, [sp], SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    )

    run_bulk_status_job(str(job.pk))

    sp.refresh_from_db()
    assert sp.status == SimulationProjet.STATUS_PROCESSING
    job.refresh_from_db()
    assert job.status == BulkStatusJob.STATUS_DONE
    assert job.processed == 1
    assert len(job.errors) == 1
    assert "notifié" in job.errors[0]["message"]
