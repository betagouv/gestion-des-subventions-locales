from celery import shared_task
from django.core.exceptions import ValidationError
from django_fsm import TransitionNotAllowed

from gsl.core.models import BulkActionsJob
from gsl_demarches_simplifiees.exceptions import DsServiceException

from .forms import SimulationProjetStatusForm
from .models import BULK_STATUS_ACTION, SimulationProjet


@shared_task
def run_bulk_status_job(job_id: str) -> None:
    """
    Apply a target status to every SimulationProjet referenced by `job`,
    one row at a time. DN mutations run per row (via the form), so a failure
    on one row is recorded and the next row is attempted.
    """
    job = BulkActionsJob.objects.select_related("created_by").get(
        pk=job_id, action=BULK_STATUS_ACTION
    )
    try:
        job.status = BulkActionsJob.STATUS_RUNNING
        job.save(update_fields=["status", "updated_at"])

        simulation_projets = (
            SimulationProjet.objects.filter(
                simulation_id=job.params["simulation_id"],
                id__in=job.object_ids,
            )
            .select_related(
                "enveloppe_projet",
                "enveloppe_projet__projet",
                "enveloppe_projet__projet__dossier_ds",
                "simulation",
                "simulation__enveloppe",
            )
            .order_by("id")
        )

        for simulation_projet in simulation_projets.iterator():
            error = _process_one(job, simulation_projet)
            if error:
                job.record_error(**error)
            else:
                job.record_success()

        job.status = BulkActionsJob.STATUS_DONE
        job.save(update_fields=["status", "updated_at"])
    finally:
        # Last-resort safety net: if an unexpected exception propagated out of
        # the loop (programming error, DB outage, etc.), mark the job DONE with
        # a crash sentinel so the UI stops polling, then re-raise so Celery and
        # Sentry see the traceback. Per-row expected failures are caught
        # narrowly in _process_one and recorded as row-level errors instead.
        current = (
            BulkActionsJob.objects.filter(pk=job.pk).only("status", "errors").first()
        )
        if current is not None and current.status != BulkActionsJob.STATUS_DONE:
            crash_error = {
                "object_id": None,
                "label": "Traitement",
                "message": "Erreur inattendue : le traitement a été interrompu.",
            }
            current.errors = [*current.errors, crash_error]
            current.status = BulkActionsJob.STATUS_DONE
            current.save(update_fields=["status", "errors", "updated_at"])


def _process_one(
    job: BulkActionsJob, simulation_projet: SimulationProjet
) -> dict | None:
    label = simulation_projet.projet.dossier_ds.projet_intitule or str(
        simulation_projet.pk
    )

    if simulation_projet.projet.has_been_notified:
        return _error(
            simulation_projet, label, "Le projet a été notifié depuis la sélection."
        )

    form = SimulationProjetStatusForm(
        data={}, instance=simulation_projet, status=job.params["target_status"]
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
            "le changement de statut n'est plus possible.",
        )
    except ValidationError as exc:
        return _error(simulation_projet, label, "; ".join(exc.messages))

    return None


def _error(simulation_projet: SimulationProjet, label: str, message: str) -> dict:
    return {
        "object_id": simulation_projet.pk,
        "label": label,
        "message": message,
    }
