from django.db import IntegrityError
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView

from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_CHANGEMENT_STATUT_BULK,
    MATOMO_CATEGORY_SIMULATION,
)
from gsl_projet.constants import DOTATIONS
from gsl_simulation.forms import BulkStatusJobForm
from gsl_simulation.models import BulkStatusJob, Simulation, SimulationProjet
from gsl_simulation.table_columns import SIMULATION_TABLE_COLUMNS
from gsl_simulation.tasks import run_bulk_status_job

BULK_STATUS_MODAL_ID = "bulk-status-confirm-modal"


@method_decorator(htmx_only, name="dispatch")
class BulkStatusJobStartView(CreateView):
    """
    Creates a BulkStatusJob for the selected SimulationProjets and enqueues the
    Celery task. Responds with the progress partial, swapped into the
    confirmation modal's body (innerHTML). Subsequent updates come from
    `BulkStatusJobProgressView` polling.
    """

    model = BulkStatusJob
    form_class = BulkStatusJobForm
    http_method_names = ["post"]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def _render_already_running(self):
        return render(
            self.request,
            "htmx/bulk_status_already_running_modal.html",
            {
                "modal_id": BULK_STATUS_MODAL_ID,
                "modal_button_id": f"{BULK_STATUS_MODAL_ID}-button",
            },
        )

    def form_invalid(self, form):
        if any(
            getattr(err, "code", None) == "already_running"
            for err in form.non_field_errors().as_data()
        ):
            return self._render_already_running()
        raise Http404(user_message="Requête invalide")

    def form_valid(self, form):
        try:
            job = form.save()
        except IntegrityError:
            # Race: a concurrent request passed Form.clean's check and created
            # an active job for the same simulation between our check and save.
            # The DB-level partial unique constraint catches the duplicate.
            return self._render_already_running()
        run_bulk_status_job.delay(str(job.pk))

        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_SIMULATION,
            MATOMO_ACTION_CHANGEMENT_STATUT_BULK,
            f"{job.target_status}:{job.total}",
        )

        return render(
            self.request,
            "htmx/_bulk_status_progress_partial.html",
            {
                "job": job,
                "modal_id": BULK_STATUS_MODAL_ID,
                "simulation_projets_to_refresh": [],
            },
        )


@method_decorator(htmx_only, name="dispatch")
class BulkStatusJobProgressView(DetailView):
    """
    Polled every 500 ms while the job is running. Returns the progress div —
    identical shape to the start response — so HTMX outerHTML swap preserves
    the polling trigger until the job is done.
    """

    model = BulkStatusJob
    template_name = "htmx/_bulk_status_progress_partial.html"
    context_object_name = "job"

    def get_queryset(self):
        return BulkStatusJob.objects.filter(
            created_by=self.request.user,
            simulation__in=Simulation.objects.visible_for_user(self.request.user),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modal_id"] = BULK_STATUS_MODAL_ID
        simulation_projets_to_refresh = self._get_simulation_projets_to_refresh()
        context["simulation_projets_to_refresh"] = simulation_projets_to_refresh
        context["selectable_ids_list"] = [
            sp.id
            for sp in simulation_projets_to_refresh
            if sp.status in BulkStatusJob.ALLOWED_TARGET_STATUSES
            and sp.dotation_projet.projet.notified_at is None
        ]
        context["columns"] = SIMULATION_TABLE_COLUMNS
        context["dotations"] = DOTATIONS
        return context

    def _get_simulation_projets_to_refresh(self):
        if self.object.status != BulkStatusJob.STATUS_DONE:
            return []
        return list(
            SimulationProjet.objects.filter(
                id__in=self.object.simulation_projet_ids,
            )
            .select_related(
                "simulation",
                "simulation__enveloppe",
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
            )
            .prefetch_related("dotation_projet__projet__dotationprojet_set")
        )
