from celery import shared_task
from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils import timezone
from django_fsm import TransitionNotAllowed

from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_simulation.forms import SimulationProjetStatusForm
from gsl_simulation.models import BulkStatusJob, SimulationProjet


@shared_task
def run_bulk_status_job(job_id: str) -> None:
    """
    Apply a target status to every SimulationProjet referenced by `job`,
    one row at a time. DN mutations run per row (via the form), so a failure
    on one row is recorded and the next row is attempted.
    """
    job = BulkStatusJob.objects.select_related("created_by").get(pk=job_id)
    errors = []
    try:
        job.status = BulkStatusJob.STATUS_RUNNING
        job.save(update_fields=["status", "updated_at"])

        simulation_projets = (
            SimulationProjet.objects.filter(
                simulation=job.simulation,
                id__in=job.simulation_projet_ids,
            )
            .select_related(
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
                "simulation",
                "simulation__enveloppe",
            )
            .order_by("id")
        )

        for simulation_projet in simulation_projets.iterator():
            error = _process_one(job, simulation_projet)
            if error:
                errors.append(error)
            BulkStatusJob.objects.filter(pk=job.pk).update(
                processed=F("processed") + 1,
                updated_at=timezone.now(),
            )

        job.errors = errors
        job.status = BulkStatusJob.STATUS_DONE
        job.save(update_fields=["status", "errors", "updated_at"])
    finally:
        # Last-resort safety net: if an unexpected exception propagated out of
        # the loop (programming error, DB outage, etc.), mark the job DONE with
        # a crash sentinel so the UI stops polling, then re-raise so Celery and
        # Sentry see the traceback. Per-row expected failures are caught
        # narrowly in _process_one and recorded as row-level errors instead.
        current = (
            BulkStatusJob.objects.filter(pk=job.pk).only("status", "errors").first()
        )
        if current is not None and current.status != BulkStatusJob.STATUS_DONE:
            crash_error = {
                "simulation_projet_id": None,
                "label": "Traitement",
                "message": "Erreur inattendue : le traitement a été interrompu.",
            }
            current.errors = [*errors, crash_error]
            current.status = BulkStatusJob.STATUS_DONE
            current.save(update_fields=["status", "errors", "updated_at"])


def _process_one(
    job: BulkStatusJob, simulation_projet: SimulationProjet
) -> dict | None:
    label = simulation_projet.projet.dossier_ds.projet_intitule or str(
        simulation_projet.pk
    )

    if simulation_projet.projet.notified_at is not None:
        return _error(
            simulation_projet, label, "Le projet a été notifié depuis la sélection."
        )

    form = SimulationProjetStatusForm(
        data={}, instance=simulation_projet, status=job.target_status
    )
    if not form.is_valid():
        message = "; ".join(
            str(msg)
            for msgs in form.errors.values()
            for msg in (msgs if isinstance(msgs, list) else [msgs])
        )
        return _error(simulation_projet, label, message)

    try:
        form.save(user=job.created_by)
    except DsServiceException as exc:
        return _error(simulation_projet, label, str(exc) or type(exc).__name__)
    except TransitionNotAllowed:
        return _error(
            simulation_projet,
            label,
            "Le statut du projet a changé depuis la sélection, "
            "la transition n'est plus possible.",
        )
    except ValidationError as exc:
        return _error(simulation_projet, label, "; ".join(exc.messages))

    return None


def _error(simulation_projet: SimulationProjet, label: str, message: str) -> dict:
    return {
        "simulation_projet_id": simulation_projet.pk,
        "label": label,
        "message": message,
    }
