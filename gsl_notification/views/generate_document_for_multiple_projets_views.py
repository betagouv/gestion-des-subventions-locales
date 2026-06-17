import logging

from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django_htmx.http import trigger_client_event
from formtools.wizard.views import SessionWizardView

from gsl.celery import TASK_PRIORITY_HIGH
from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_notification.forms import (
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
    SELECTED_TYPES_BY_CHOICE,
    GenerateDocumentsCreateForm,
    GenerateDocumentsLaunchForm,
    GenerateDocumentsStep1Form,
    GenerateDocumentsStep2Form,
    GenerateDocumentsStep3Form,
)
from gsl_notification.models import ExportJob
from gsl_notification.tasks import generate_export_task
from gsl_notification.utils import get_programmation_projet_attribute
from gsl_projet.constants import DOTATIONS

logger = logging.getLogger(__name__)


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsWizard(SessionWizardView):
    LAUNCH_STEP = "launch"
    STEP1 = "step1"  # type de document
    STEP2 = "step2"  # choix des modèles + stratégie
    STEP3 = "step3"  # format d'export
    STEP4 = "step4"  # création (no-op form, déclenché par render_done)

    TEMPLATE_BASE = "gsl_notification/generated_document/multiple/"
    SUCCESS_TEMPLATE = TEMPLATE_BASE + "modal_success_body.html"
    POLLING_TEMPLATE = TEMPLATE_BASE + "modal_export_progress_body.html"
    ERROR_TEMPLATE = TEMPLATE_BASE + "modal_export_error_body.html"

    form_list = [
        (LAUNCH_STEP, GenerateDocumentsLaunchForm),
        (STEP1, GenerateDocumentsStep1Form),
        (STEP2, GenerateDocumentsStep2Form),
        (STEP3, GenerateDocumentsStep3Form),
        (STEP4, GenerateDocumentsCreateForm),
    ]
    FORM_STEP_TEMPLATE = TEMPLATE_BASE + "modal_form_step_body.html"
    TEMPLATES = {
        LAUNCH_STEP: TEMPLATE_BASE + "modal_launch_error_body.html",
        STEP1: FORM_STEP_TEMPLATE,
        STEP2: TEMPLATE_BASE + "modal_step2_body.html",
        STEP3: FORM_STEP_TEMPLATE,
        STEP4: TEMPLATE_BASE + "modal_loading_body.html",
    }
    STEPPER_META = {
        STEP1: (1, "Types de document", "Choix des modèles"),
        STEP3: (3, "Format d'export", "Téléchargement"),
    }
    modal_id = "generate-multiple-modal"

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("dotation") not in DOTATIONS:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    def get_prefix(self, request, *args, **kwargs):
        # Namespace storage by dotation so DETR and DSIL don't collide.
        return f"{super().get_prefix(request, *args, **kwargs)}_{kwargs['dotation']}"

    def post(self, request, *args, **kwargs):
        # Read the submitted step from the management form, not from storage:
        # storage may still hold a non-launch step from a previously abandoned
        # wizard run, which would mask "this is a launch submission" and prevent
        # _is_initial_modal_render() from triggering the modal-open event.
        self._submitted_step = request.POST.get(f"{self.prefix}-current_step")
        return super().post(request, *args, **kwargs)

    def get_cleaned_data_for_step(self, step):
        # formtools re-instantiates and re-validates the step's form on every
        # call. Within one request, the underlying storage data for a non-current
        # step doesn't change, so we cache the result per instance.
        if not hasattr(self, "_cleaned_data_cache"):
            self._cleaned_data_cache = {}
        if step not in self._cleaned_data_cache:
            self._cleaned_data_cache[step] = super().get_cleaned_data_for_step(step)
        return self._cleaned_data_cache[step]

    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        kwargs.update(
            {
                "user": self.request.user,
                "dotation": self.kwargs["dotation"],
                "request": self.request,
            }
        )
        if step in (self.STEP2, self.STEP3, self.STEP4):
            step1_data = self.get_cleaned_data_for_step(self.STEP1) or {}
            kwargs["document_type"] = step1_data.get("document_type")
        if step in (self.STEP2, self.STEP4):
            launch_data = self.get_cleaned_data_for_step(self.LAUNCH_STEP) or {}
            kwargs["programmation_projets"] = launch_data.get("ids") or []
        return kwargs

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context["dotation"] = self.kwargs["dotation"]
        context["modal_id"] = self.modal_id
        context["modal_button_id"] = f"{self.modal_id}-button"
        if stepper := self.STEPPER_META.get(self.steps.current):
            (
                context["current_step_id"],
                context["current_step_title"],
                context["next_step_title"],
            ) = stepper
        if self.steps.current in (self.STEP3, self.STEP4):
            launch_data = self.get_cleaned_data_for_step(self.LAUNCH_STEP) or {}
            step1_data = self.get_cleaned_data_for_step(self.STEP1) or {}
            ids = launch_data.get("ids") or []
            document_type = step1_data.get("document_type")
            if document_type:
                context["doc_count"] = len(ids) * len(
                    SELECTED_TYPES_BY_CHOICE[document_type]
                )
        return context

    def _is_initial_modal_render(self):
        # Response to a launch POST (validation failure stays on launch; success
        # advances to step1). Either way the modal isn't open yet, so we render
        # the full <dialog> wrapper plus the hidden trigger button.
        return getattr(self, "_submitted_step", None) == self.LAUNCH_STEP

    def get_template_names(self):
        return [self.TEMPLATES[self.steps.current]]

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        if self._is_initial_modal_render():
            return trigger_client_event(
                response,
                "click",
                {"target": f"#{self.modal_id}-button"},
                after="settle",
            )
        return response

    def render_next_step(self, form, **kwargs):
        if self.steps.current == self.LAUNCH_STEP:
            # Wipe leftover progress from a previous wizard run while preserving
            # the just-validated launch data.
            launch_data = self.storage.get_step_data(self.LAUNCH_STEP)
            self.storage.reset()
            self.storage.set_step_data(self.LAUNCH_STEP, launch_data)
            self.storage.current_step = self.LAUNCH_STEP
        return super().render_next_step(form, **kwargs)

    def render_done(self, form, **kwargs):
        form_dict = {
            step: self.get_form(
                step=step,
                data=self.storage.get_step_data(step),
                files=self.storage.get_step_files(step),
            )
            for step in self.get_form_list()
        }
        # Only validate the steps whose cleaned_data is read from form_dict in
        # done(). LAUNCH and STEP1 feed into other steps via get_form_kwargs,
        # where they were already validated (and cached). STEP4 is the
        # save-action form, not a data-bearing step.
        for step in (self.STEP2, self.STEP3):
            form_dict[step].is_valid()
        response = self.done(form_dict.values(), form_dict=form_dict, **kwargs)
        self.storage.reset()
        return response

    def done(self, form_list, form_dict, **kwargs):
        form = form_dict[self.STEP4]
        step2_data = form_dict[self.STEP2].cleaned_data
        step3_data = form_dict[self.STEP3].cleaned_data
        export_format = step3_data.get("export_format")
        with_qr_code = step3_data.get("with_qr_code")

        refreshed = form.save(
            modele_arrete=step2_data.get("modele_arrete_id"),
            modele_lettre=step2_data.get("modele_lettre_id"),
            overwrite_strategy=step2_data.get("overwrite_strategy"),
        )

        attrs = [get_programmation_projet_attribute(t) for t in form.selected_types]
        pp_ids = [pp.pk for pp in refreshed]

        job = ExportJob.objects.create(
            created_by=self.request.user,
            pp_ids=pp_ids,
            attr_names=attrs,
            export_format=export_format,
            document_type=form.document_type,
            with_qr_code=with_qr_code,
        )
        generate_export_task.apply_async(
            args=[str(job.pk)],
            priority=TASK_PRIORITY_HIGH,
        )

        return render(
            self.request,
            self.POLLING_TEMPLATE,
            {
                "job_id": str(job.pk),
                "job": job,
                "modal_id": self.modal_id,
                "dotation": self.kwargs["dotation"],
            },
        )


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsStatusView(View):
    """Polled every 2 s while the export job is running."""

    TEMPLATE_BASE = GenerateDocumentsWizard.TEMPLATE_BASE
    SUCCESS_TEMPLATE = GenerateDocumentsWizard.SUCCESS_TEMPLATE
    POLLING_TEMPLATE = GenerateDocumentsWizard.POLLING_TEMPLATE
    ERROR_TEMPLATE = GenerateDocumentsWizard.ERROR_TEMPLATE

    def get(self, request, dotation, job_id):
        from gsl_programmation.models import ProgrammationProjet

        job = ExportJob.objects.get(pk=job_id)
        context = {
            "modal_id": GenerateDocumentsWizard.modal_id,
            "dotation": dotation,
            "job_id": str(job.pk),
            "job": job,
        }

        if job.is_running:
            return render(request, self.POLLING_TEMPLATE, context)

        if job.status == ExportJob.STATUS_DONE:
            pp_ids = job.pp_ids
            refreshed = list(
                ProgrammationProjet.objects.filter(pk__in=pp_ids)
                .select_related(
                    "arrete", "lettre_notification", "lettre_et_arrete_signes"
                )
                .prefetch_related("annexes")
            )
            pk_to_pp = {pp.pk: pp for pp in refreshed}
            refreshed_ordered = [pk_to_pp[pk] for pk in pp_ids if pk in pk_to_pp]
            export_format = job.export_format
            context.update(
                {
                    "download_url": job.download_url,
                    "doc_count": len(pp_ids) * len(job.attr_names),
                    "is_export_one_pdf_all": export_format == EXPORT_FORMAT_ONE_PDF_ALL,
                    "is_export_one_pdf_all_grouped": export_format
                    == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
                    "is_export_one_pdf_per_project": export_format
                    == EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
                    "refreshed_programmation_projets": refreshed_ordered,
                }
            )
            return render(request, self.SUCCESS_TEMPLATE, context)

        return render(request, self.ERROR_TEMPLATE, context)
