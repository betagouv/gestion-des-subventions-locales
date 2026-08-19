import logging

from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import DetailView
from django_htmx.http import trigger_client_event
from formtools.wizard.views import SessionWizardView

from gsl.celery import TASK_PRIORITY_NORMAL
from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_notification.forms import (
    DOCUMENT_TYPE_DISPLAY_ORDER,
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
    SELECTED_TYPES_BY_CHOICE,
    GenerateDocumentsCreateForm,
    GenerateDocumentsFormatForm,
    GenerateDocumentsLaunchForm,
    GenerateDocumentsModeleSelectionForm,
    GenerateDocumentsTypeSelectionForm,
    GenerateRefusLettersCreateForm,
)
from gsl_notification.models import ExportJob
from gsl_notification.tasks import generate_export_task
from gsl_projet.constants import DOTATIONS, LETTRE_REFUS

logger = logging.getLogger(__name__)


@method_decorator(htmx_only, name="dispatch")
class BaseGenerateDocumentsWizard(SessionWizardView):
    """
    Shared plumbing for the "generate accepted documents" and "generate
    lettre de refus" multi-projet wizards: both are launch -> ... -> create
    SessionWizardView flows, sharing the same step names and forms — the
    only structural difference is the optional TYPE_SELECTION_STEP.

    Subclasses must set:
    - PREFIX: the literal storage/HTML prefix. Deliberately NOT derived from
      the class name (formtools' default), so renaming a subclass never
      changes the session storage key or the HTML field names.
    - HAS_TYPE_SELECTION_STEP: whether this wizard includes the "type de
      document" step. Only GenerateAcceptedDocumentsWizard does — a refus
      letters run has a single, fixed document type. TOTAL_STEPS, form_list
      and TEMPLATES are all derived from this flag in __init_subclass__.
    - CREATE_FORM_CLASS: the form invoked at CREATE_STEP.
    - DOCUMENT_TYPE: the fixed document_type. Only needed when
      HAS_TYPE_SELECTION_STEP is False — otherwise it's resolved from the
      TYPE_SELECTION_STEP form.
    - MODAL_TITLE: fed to the shared modal templates.
    - MODAL_POST_URL_NAME, STATUS_URL_NAME: this wizard's own URL names,
      used by the shared templates (form actions, polling endpoint).
    - STEPPER_META, modal_id: presentation details that genuinely differ per
      wizard (step numbering/wording, DOM ids).
    - get_save_kwargs(merged_data).
    """

    LAUNCH_STEP = "launch"
    TYPE_SELECTION_STEP = "type_selection"
    MODELE_SELECTION_STEP = "modele_selection"
    FORMAT_STEP = "format"
    CREATE_STEP = "create"

    # Identical for both wizards now that step names are shared.
    DOC_COUNT_STEPS = (FORMAT_STEP, CREATE_STEP)
    DONE_STEPS = (MODELE_SELECTION_STEP, FORMAT_STEP)

    HAS_TYPE_SELECTION_STEP: bool = False
    CREATE_FORM_CLASS: type = None
    DOCUMENT_TYPE: str = ""

    PREFIX: str = ""
    MODAL_TITLE: str = ""
    TOTAL_STEPS: int = 0
    MODAL_POST_URL_NAME: str = ""
    STATUS_URL_NAME: str = ""

    # Templates shared by both wizards — only the content-specific step
    # (chosen per subclass in its TEMPLATES dict) needs its own template.
    TEMPLATE_BASE = "gsl_notification/generated_document/multiple_wizard/"
    LAUNCH_TEMPLATE = TEMPLATE_BASE + "modal_launch.html"
    FORMAT_STEP_TEMPLATE = TEMPLATE_BASE + "modal_format_step.html"
    MODELE_SELECTION_STEP_TEMPLATE = TEMPLATE_BASE + "modal_modele_selection.html"
    LOADING_TEMPLATE = TEMPLATE_BASE + "modal_loading.html"
    POLLING_TEMPLATE = TEMPLATE_BASE + "modal_export_progress.html"
    SUCCESS_TEMPLATE = TEMPLATE_BASE + "modal_success.html"
    ERROR_TEMPLATE = TEMPLATE_BASE + "modal_export_error.html"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.CREATE_FORM_CLASS is None:
            return  # abstract subclass, if any

        steps = [(cls.LAUNCH_STEP, GenerateDocumentsLaunchForm)]
        if cls.HAS_TYPE_SELECTION_STEP:
            steps.append((cls.TYPE_SELECTION_STEP, GenerateDocumentsTypeSelectionForm))
        steps += [
            (cls.MODELE_SELECTION_STEP, GenerateDocumentsModeleSelectionForm),
            (cls.FORMAT_STEP, GenerateDocumentsFormatForm),
            (cls.CREATE_STEP, cls.CREATE_FORM_CLASS),
        ]
        cls.form_list = steps
        cls.TOTAL_STEPS = len(steps) - 1  # LAUNCH_STEP isn't shown in the stepper

        cls.TEMPLATES = {
            cls.LAUNCH_STEP: cls.LAUNCH_TEMPLATE,
            cls.MODELE_SELECTION_STEP: cls.MODELE_SELECTION_STEP_TEMPLATE,
            cls.FORMAT_STEP: cls.FORMAT_STEP_TEMPLATE,
            cls.CREATE_STEP: cls.LOADING_TEMPLATE,
        }
        if cls.HAS_TYPE_SELECTION_STEP:
            cls.TEMPLATES[cls.TYPE_SELECTION_STEP] = cls.FORMAT_STEP_TEMPLATE

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("dotation") not in DOTATIONS:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    def get_prefix(self, request, *args, **kwargs):
        # Namespace storage by dotation so DETR and DSIL don't collide. Uses
        # PREFIX rather than super().get_prefix() (which derives from
        # self.__class__.__name__) so the prefix stays stable across renames.
        return f"{self.PREFIX}_{kwargs['dotation']}"

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
        kwargs.update(self.get_extra_form_kwargs(step))
        return kwargs

    def get_document_type(self):
        if self.HAS_TYPE_SELECTION_STEP:
            type_selection_data = (
                self.get_cleaned_data_for_step(self.TYPE_SELECTION_STEP) or {}
            )
            return type_selection_data.get("document_type")
        return self.DOCUMENT_TYPE

    def get_extra_form_kwargs(self, step):
        kwargs = {}
        if step in (self.MODELE_SELECTION_STEP, self.FORMAT_STEP, self.CREATE_STEP) or (
            step == self.LAUNCH_STEP and not self.HAS_TYPE_SELECTION_STEP
        ):
            kwargs["document_type"] = self.get_document_type()
        if step in (self.MODELE_SELECTION_STEP, self.CREATE_STEP):
            launch_data = self.get_cleaned_data_for_step(self.LAUNCH_STEP) or {}
            kwargs["programmation_projets"] = launch_data.get("ids") or []
        return kwargs

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context["dotation"] = self.kwargs["dotation"]
        context["modal_id"] = self.modal_id
        context["modal_button_id"] = f"{self.modal_id}-button"
        context["modal_title"] = self.MODAL_TITLE
        context["total_steps"] = self.TOTAL_STEPS
        context["modal_post_url_name"] = self.MODAL_POST_URL_NAME
        if stepper := self.STEPPER_META.get(self.steps.current):
            (
                context["current_step_id"],
                context["current_step_title"],
                context["next_step_title"],
            ) = stepper
        if self.steps.current in self.DOC_COUNT_STEPS:
            launch_data = self.get_cleaned_data_for_step(self.LAUNCH_STEP) or {}
            ids = launch_data.get("ids") or []
            document_type = self.get_extra_form_kwargs(self.CREATE_STEP).get(
                "document_type"
            )
            if document_type:
                context["doc_count"] = len(ids) * len(
                    SELECTED_TYPES_BY_CHOICE[document_type]
                )
        return context

    def _is_initial_modal_render(self):
        # Response to a launch POST (validation failure stays on launch; success
        # advances to the next step). Either way the modal isn't open yet, so we
        # render the full <dialog> wrapper plus the hidden trigger button.
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
        # Only validate the steps whose cleaned_data is read by done(). Other
        # data-bearing steps feed into later steps via get_form_kwargs, where
        # they were already validated (and cached). CREATE_STEP is the
        # save-action form, not a data-bearing step.
        for step in self.DONE_STEPS:
            form_dict[step].is_valid()
        response = self.done(form_dict.values(), form_dict=form_dict, **kwargs)
        self.storage.reset()
        return response

    def done(self, form_list, form_dict, **kwargs):
        form = form_dict[self.CREATE_STEP]
        merged_data = {}
        for step in self.DONE_STEPS:
            merged_data.update(form_dict[step].cleaned_data)
        export_format = merged_data.get("export_format")
        with_qr_code = merged_data.get("with_qr_code")

        refreshed = form.save(**self.get_save_kwargs(merged_data))

        # attr_names is stored as JSON: selected_types is a frozenset, so pin a
        # deterministic order (lettre before arrete before refus, matching the
        # wizards' display order elsewhere) rather than storing the set itself.
        attrs = [t for t in DOCUMENT_TYPE_DISPLAY_ORDER if t in form.selected_types]
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
            priority=TASK_PRIORITY_NORMAL,
        )

        return render(
            self.request,
            self.POLLING_TEMPLATE,
            {
                "job_id": str(job.pk),
                "job": job,
                "modal_id": self.modal_id,
                "dotation": self.kwargs["dotation"],
                "modal_title": self.MODAL_TITLE,
                "total_steps": self.TOTAL_STEPS,
                "status_url_name": self.STATUS_URL_NAME,
            },
        )

    def get_save_kwargs(self, merged_data):
        """Kwargs passed to the create-step form's save(). Overridden by
        subclasses."""
        raise NotImplementedError


class GenerateAcceptedDocumentsWizard(BaseGenerateDocumentsWizard):
    HAS_TYPE_SELECTION_STEP = True
    CREATE_FORM_CLASS = GenerateDocumentsCreateForm

    PREFIX = "generate_documents_wizard"
    MODAL_TITLE = "Générer les documents"
    MODAL_POST_URL_NAME = "gsl_notification:generate-documents-modal"
    STATUS_URL_NAME = "gsl_notification:generate-documents-status"

    STEPPER_META = {
        BaseGenerateDocumentsWizard.TYPE_SELECTION_STEP: (
            1,
            "Types de document",
            "Choix des modèles",
        ),
        BaseGenerateDocumentsWizard.MODELE_SELECTION_STEP: (
            2,
            "Choix des modèles",
            "Format d'export",
        ),
        BaseGenerateDocumentsWizard.FORMAT_STEP: (
            3,
            "Format d'export",
            "Téléchargement",
        ),
    }
    modal_id = "generate-multiple-modal"

    def get_save_kwargs(self, merged_data):
        return {
            "modele_arrete": merged_data.get("modele_arrete_id"),
            "modele_lettre": merged_data.get("modele_lettre_id"),
            "overwrite_strategy": merged_data.get("overwrite_strategy"),
        }


class GenerateLettreRefusWizard(BaseGenerateDocumentsWizard):
    """
    Same flow as GenerateAcceptedDocumentsWizard, without the "type de
    document" step: there's only one document type (LETTRE_REFUS).
    """

    HAS_TYPE_SELECTION_STEP = False
    CREATE_FORM_CLASS = GenerateRefusLettersCreateForm
    DOCUMENT_TYPE = LETTRE_REFUS

    PREFIX = "generate_refus_wizard"
    MODAL_TITLE = "Générer les lettres de refus ou de classement sans suite"
    MODAL_POST_URL_NAME = "gsl_notification:generate-refus-documents-modal"
    STATUS_URL_NAME = "gsl_notification:generate-refus-documents-status"

    STEPPER_META = {
        BaseGenerateDocumentsWizard.MODELE_SELECTION_STEP: (
            1,
            "Choix du modèle",
            "Format d'export",
        ),
        BaseGenerateDocumentsWizard.FORMAT_STEP: (
            2,
            "Format d'export",
            "Téléchargement",
        ),
    }
    modal_id = "generate-refus-modal"

    def get_save_kwargs(self, merged_data):
        return {
            "modele_refus": merged_data.get("modele_refus_id"),
            "overwrite_strategy": merged_data.get("overwrite_strategy"),
        }


@method_decorator(htmx_only, name="dispatch")
class BaseGenerateDocumentsStatusView(DetailView):
    """
    Polled every 2 s while an export job started by a BaseGenerateDocumentsWizard
    is running.

    Subclasses must set:
    - WIZARD_CLASS: the paired wizard, which supplies modal_id and templates.
    - SELECT_RELATED / PREFETCH_RELATED: relations to fetch on the refreshed
      ProgrammationProjet queryset once the job is done.
    """

    model = ExportJob
    pk_url_kwarg = "job_id"

    WIZARD_CLASS: type = None
    SELECT_RELATED: tuple[str, ...] = ()
    PREFETCH_RELATED: tuple[str, ...] = ()

    def get_queryset(self):
        return ExportJob.objects.filter(created_by=self.request.user)

    def get(self, request, dotation, **_):
        from gsl_programmation.models import ProgrammationProjet

        job = self.get_object()
        context = {
            "modal_id": self.WIZARD_CLASS.modal_id,
            "dotation": dotation,
            "job_id": str(job.pk),
            "job": job,
            "modal_title": self.WIZARD_CLASS.MODAL_TITLE,
            "total_steps": self.WIZARD_CLASS.TOTAL_STEPS,
            "status_url_name": self.WIZARD_CLASS.STATUS_URL_NAME,
        }

        if job.is_running:
            return render(request, self.WIZARD_CLASS.POLLING_TEMPLATE, context)

        if job.status == ExportJob.STATUS_DONE:
            pp_ids = job.pp_ids
            qs = ProgrammationProjet.objects.filter(pk__in=pp_ids)
            if self.SELECT_RELATED:
                qs = qs.select_related(*self.SELECT_RELATED)
            if self.PREFETCH_RELATED:
                qs = qs.prefetch_related(*self.PREFETCH_RELATED)
            refreshed = list(qs)
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
            response = render(request, self.WIZARD_CLASS.SUCCESS_TEMPLATE, context)
            return trigger_client_event(response, "documents-generated")

        return render(request, self.WIZARD_CLASS.ERROR_TEMPLATE, context)


class GenerateAcceptedDocumentsStatusView(BaseGenerateDocumentsStatusView):
    WIZARD_CLASS = GenerateAcceptedDocumentsWizard
    SELECT_RELATED = ("arrete", "lettrenotification", "lettre_et_arrete_signes")
    PREFETCH_RELATED = ("annexes",)


class GenerateLettreRefusStatusView(BaseGenerateDocumentsStatusView):
    WIZARD_CLASS = GenerateLettreRefusWizard
    SELECT_RELATED = ("lettrerefus",)
