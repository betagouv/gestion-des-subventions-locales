from unittest import mock

import pytest
from django.db import IntegrityError
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR, PROJET_STATUS_PROCESSING
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import BulkStatusJob, SimulationProjet
from gsl_simulation.tests.factories import (
    SimulationFactory,
    SimulationProjetFactory,
    make_detr_simu_projet,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def enveloppe(perimetre):
    return DetrEnveloppeFactory(perimetre=perimetre, annee=2025, montant=1_000_000)


@pytest.fixture
def simulation(enveloppe):
    return SimulationFactory(enveloppe=enveloppe)


@pytest.fixture
def collegue(perimetre):
    return CollegueWithDSProfileFactory(perimetre=perimetre)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


def _make_simu_projet(collegue, simulation, **kwargs):
    return make_detr_simu_projet(collegue.perimetre, simulation, **kwargs)


def test_start_view_creates_job_and_enqueues_task(
    client_with_user_logged, collegue, simulation
):
    sp1 = _make_simu_projet(collegue, simulation)
    sp2 = _make_simu_projet(collegue, simulation)

    with mock.patch(
        "gsl_simulation.views.bulk_status_job_views.run_bulk_status_job.delay"
    ) as task_delay:
        response = client_with_user_logged.post(
            reverse("simulation:bulk-status-job-start"),
            data={
                "simulation": simulation.pk,
                "target_status": SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
                "simulation_projet_ids": f"{sp1.id},{sp2.id}",
            },
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert BulkStatusJob.objects.count() == 1
    job = BulkStatusJob.objects.get()
    assert job.simulation == simulation
    assert job.created_by == collegue
    assert job.target_status == SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    assert sorted(job.simulation_projet_ids) == sorted([sp1.id, sp2.id])
    assert job.total == 2
    assert job.processed == 0
    task_delay.assert_called_once_with(str(job.pk))
    assert b"bulk-status-progress-body" in response.content
    assert b"every 500ms" in response.content


def test_start_view_rejects_invalid_target_status(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)
    with mock.patch(
        "gsl_simulation.views.bulk_status_job_views.run_bulk_status_job.delay"
    ) as task_delay:
        response = client_with_user_logged.post(
            reverse("simulation:bulk-status-job-start"),
            data={
                "simulation": simulation.pk,
                "target_status": SimulationProjet.STATUS_REFUSED,
                "simulation_projet_ids": f"{sp.id}",
            },
            headers={"HX-Request": "true"},
        )
    assert response.status_code == 404
    assert BulkStatusJob.objects.count() == 0
    task_delay.assert_not_called()


def test_start_view_rejects_foreign_perimeter_ids(
    client_with_user_logged, collegue, simulation
):
    mine = _make_simu_projet(collegue, simulation)
    other_perim = PerimetreDepartementalFactory()
    other_env = DetrEnveloppeFactory(perimetre=other_perim, annee=2025)
    other_simu = SimulationFactory(enveloppe=other_env)
    other_dp = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=other_perim,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    outsider = SimulationProjetFactory(
        dotation_projet=other_dp,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=1000,
        simulation=other_simu,
    )

    with mock.patch(
        "gsl_simulation.views.bulk_status_job_views.run_bulk_status_job.delay"
    ):
        response = client_with_user_logged.post(
            reverse("simulation:bulk-status-job-start"),
            data={
                "simulation": simulation.pk,
                "target_status": SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
                "simulation_projet_ids": f"{mine.id},{outsider.id}",
            },
            headers={"HX-Request": "true"},
        )
    assert response.status_code == 404
    assert BulkStatusJob.objects.count() == 0


def test_start_view_refuses_duplicate_job_for_same_simulation(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)
    BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[sp.id],
        status=BulkStatusJob.STATUS_RUNNING,
    )

    with mock.patch(
        "gsl_simulation.views.bulk_status_job_views.run_bulk_status_job.delay"
    ) as task_delay:
        response = client_with_user_logged.post(
            reverse("simulation:bulk-status-job-start"),
            data={
                "simulation": simulation.pk,
                "target_status": SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
                "simulation_projet_ids": f"{sp.id}",
            },
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert "Traitement déjà en cours".encode() in response.content
    assert BulkStatusJob.objects.count() == 1
    task_delay.assert_not_called()


def test_db_constraint_rejects_two_active_jobs_for_same_simulation(
    collegue, simulation
):
    BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[],
        status=BulkStatusJob.STATUS_RUNNING,
    )
    with pytest.raises(IntegrityError):
        BulkStatusJob.objects.create(
            simulation=simulation,
            created_by=collegue,
            target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
            simulation_projet_ids=[],
            status=BulkStatusJob.STATUS_PENDING,
        )


def test_start_view_handles_race_with_integrity_error(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)

    with (
        mock.patch(
            "gsl_simulation.views.bulk_status_job_views.run_bulk_status_job.delay"
        ) as task_delay,
        mock.patch(
            "gsl_simulation.forms.BulkStatusJobForm.save",
            side_effect=IntegrityError("uq_bulkstatusjob_active_per_simulation"),
        ),
    ):
        response = client_with_user_logged.post(
            reverse("simulation:bulk-status-job-start"),
            data={
                "simulation": simulation.pk,
                "target_status": SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
                "simulation_projet_ids": f"{sp.id}",
            },
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert "Traitement déjà en cours".encode() in response.content
    task_delay.assert_not_called()


def test_start_view_allows_new_job_once_previous_is_done(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)
    BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[sp.id],
        status=BulkStatusJob.STATUS_DONE,
        processed=1,
    )

    with mock.patch(
        "gsl_simulation.views.bulk_status_job_views.run_bulk_status_job.delay"
    ) as task_delay:
        response = client_with_user_logged.post(
            reverse("simulation:bulk-status-job-start"),
            data={
                "simulation": simulation.pk,
                "target_status": SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
                "simulation_projet_ids": f"{sp.id}",
            },
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert BulkStatusJob.objects.count() == 2
    task_delay.assert_called_once()


def test_progress_view_returns_running_fragment_with_counts(
    client_with_user_logged, collegue, simulation
):
    job = BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[10, 20, 30, 40, 50],
        status=BulkStatusJob.STATUS_RUNNING,
        processed=2,
    )
    response = client_with_user_logged.get(
        reverse("simulation:bulk-status-job-progress", kwargs={"pk": job.pk}),
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert b"2 / 5" in response.content
    assert b"every 500ms" in response.content
    assert b"Fermer" not in response.content


def test_progress_view_returns_done_fragment_with_errors(
    client_with_user_logged, collegue, simulation
):
    job = BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[10, 20, 30],
        status=BulkStatusJob.STATUS_DONE,
        processed=3,
        errors=[
            {
                "simulation_projet_id": 123,
                "label": "Projet test",
                "message": "L'assiette est manquante.",
            }
        ],
    )
    response = client_with_user_logged.get(
        reverse("simulation:bulk-status-job-progress", kwargs={"pk": job.pk}),
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "ont bien été acceptés provisoirement".encode() in response.content
    assert b"Projet test" in response.content
    assert b"assiette est manquante" in response.content
    assert b"Fermer" in response.content
    assert b"every 500ms" not in response.content


def test_confirm_modal_is_not_closable_by_backdrop(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)

    response = client_with_user_logged.post(
        reverse(
            "simulation:simulation-projet-bulk-update-simulation-status",
            kwargs={"status": SimulationProjet.STATUS_ACCEPTED},
        ),
        data={"simulation_projet_ids": f"{sp.id}"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert b'data-fr-concealing-backdrop="false"' in response.content


def test_progress_view_running_does_not_render_row_oob(
    client_with_user_logged, collegue, simulation
):
    sp = _make_simu_projet(collegue, simulation)
    job = BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[sp.id],
        status=BulkStatusJob.STATUS_RUNNING,
        processed=0,
    )

    response = client_with_user_logged.get(
        reverse("simulation:bulk-status-job-progress", kwargs={"pk": job.pk}),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert f'id="simulation-{sp.id}"'.encode() not in response.content
    assert b'hx-swap-oob="true"' not in response.content
    assert b"Fermer" not in response.content


def test_progress_view_done_renders_row_oob_for_each_projet(
    client_with_user_logged, collegue, simulation
):
    sp1 = _make_simu_projet(collegue, simulation)
    sp2 = _make_simu_projet(collegue, simulation)
    job = BulkStatusJob.objects.create(
        simulation=simulation,
        created_by=collegue,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[sp1.id, sp2.id],
        status=BulkStatusJob.STATUS_DONE,
        processed=2,
    )

    response = client_with_user_logged.get(
        reverse("simulation:bulk-status-job-progress", kwargs={"pk": job.pk}),
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert f'id="simulation-{sp1.id}"'.encode() in response.content
    assert f'id="simulation-{sp2.id}"'.encode() in response.content
    assert response.content.count(b'hx-swap-oob="true"') >= 2
    assert b"Fermer" in response.content
    # Selectable rows keep their bulk-status checkbox after the refresh so
    # the user can immediately make a new selection.
    assert f'id="bulk-status-checkbox-{sp1.id}"'.encode() in response.content
    assert f'id="bulk-status-checkbox-{sp2.id}"'.encode() in response.content


def test_progress_view_rejects_foreign_perimeter_job(
    client_with_user_logged, collegue, simulation
):
    other_perim = PerimetreDepartementalFactory()
    other_env = DetrEnveloppeFactory(perimetre=other_perim, annee=2025)
    other_simu = SimulationFactory(enveloppe=other_env)
    other_user = CollegueWithDSProfileFactory(perimetre=other_perim)
    job = BulkStatusJob.objects.create(
        simulation=other_simu,
        created_by=other_user,
        target_status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        simulation_projet_ids=[],
    )
    response = client_with_user_logged.get(
        reverse("simulation:bulk-status-job-progress", kwargs={"pk": job.pk}),
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 404
