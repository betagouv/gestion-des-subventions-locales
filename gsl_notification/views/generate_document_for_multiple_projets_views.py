from dataclasses import dataclass, replace
from functools import cached_property

from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.utils.functional import classproperty
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
    GenerateAcceptedDocumentsLaunchForm,
    GenerateDocumentsCreateForm,
    GenerateDocumentsFormatForm,
    GenerateDocumentsModeleSelectionForm,
    GenerateDocumentsTypeSelectionForm,
    GenerateRefusLettersLaunchForm,
)
from gsl_notification.models import ExportJob
from gsl_notification.tasks import generate_export_task
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import DOTATIONS, LETTRE_REFUS


@dataclass(frozen=True)
class Step:
    """
    `form_kwargs` and `extra_context` name wizard hooks: each entry `foo` is
    resolved by calling the wizard's `get_foo()`, and passed either to the
    step's form or to its template context.
    """

    name: str
    form_class: type
    template: str
    title: str = ""
    form_kwargs: tuple[str, ...] = ()
    extra_context: tuple[str, ...] = ()


class HtmxModalWizardMixin:
    """
    Plumbing for a formtools wizard rendered inside a DSFR modal and driven by
    htmx: the page holds the modal, opens it and posts the first step; each
    response swaps the modal content in place.

    Mix into a WizardView. A wizard is entirely described by its `STEPS` and
    its modal identifiers; nothing here knows what it generates.
    """

    STEPS: tuple[Step, ...] = ()

    MODAL_TITLE: str = ""
    MODAL_POST_URL_NAME: str = ""
    modal_id: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # formtools builds the flow from form_list, read once at as_view() time.
        cls.form_list = [(step.name, step.form_class) for step in cls.STEPS]

    @classproperty
    def total_steps(cls) -> int:
        """Every step but the first, which is submitted from outside the
        modal and never appears in the stepper."""
        return len(cls.STEPS) - 1

    def get_step(self, name: str) -> Step:
        return next(step for step in self.STEPS if step.name == name)

    @property
    def current_step(self) -> Step:
        return self.get_step(self.steps.current)

    def get_hook_values(self, hook_names: tuple[str, ...]) -> dict:
        return {name: getattr(self, f"get_{name}")() for name in hook_names}

    def get_prefix(self, request, *args, **kwargs):
        prefix = super().get_prefix(request, *args, **kwargs)
        namespace = self.get_storage_namespace()
        return f"{prefix}_{namespace}" if namespace else prefix

    def get_storage_namespace(self) -> str:
        """
        Isolates concurrent runs of the same wizard from each other in the
        session storage. Subclasses override.
        """
        return ""

    @cached_property
    def _form_cache(self) -> dict:
        return {}

    def get_form_for_step(self, step):
        # A single request asks for the same step repeatedly: later steps pull
        # their kwargs from it, then render_done() needs it again. Caching is
        # safe because post() stores the submitted step's data before anything
        # reads a form back from storage.
        if step not in self._form_cache:
            self._form_cache[step] = self.get_form(
                step=step,
                data=self.storage.get_step_data(step),
                files=self.storage.get_step_files(step),
            )
        return self._form_cache[step]

    def get_cleaned_data_for_step(self, step):
        form = self.get_form_for_step(step)
        # A form validates itself only once, so asking again is free. formtools
        # expects None for a step that doesn't validate.
        return form.cleaned_data if form.is_valid() else None

    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        kwargs.update(self.get_hook_values(self.get_step(step).form_kwargs))
        return kwargs

    def get_template_names(self):
        return [self.current_step.template]

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context.update(
            {
                "modal_id": self.modal_id,
                "modal_title": self.MODAL_TITLE,
                "modal_post_url_name": self.MODAL_POST_URL_NAME,
                "total_steps": self.total_steps,
            }
        )
        context.update(self.get_stepper_context())
        context.update(self.get_hook_values(self.current_step.extra_context))
        return context

    def get_stepper_context(self) -> dict:
        stepper_steps = self.STEPS[1:]
        if self.current_step not in stepper_steps:
            return {}
        position = stepper_steps.index(self.current_step)
        next_steps = stepper_steps[position + 1 :]
        return {
            "current_step_id": position + 1,
            "current_step_title": self.current_step.title,
            "next_step_title": next_steps[0].title if next_steps else "",
        }

    def post(self, request, *args, **kwargs):
        if request.POST.get(f"{self.prefix}-current_step") == self.steps.first:
            # A new run starts: drop whatever a previous, abandoned one left in
            # the session. formtools only resets its storage once a run reaches
            # done(), and a modal can be closed at any step.
            self.storage.reset()
        return super().post(request, *args, **kwargs)

    def render_done(self, form, **kwargs):
        # The steps were submitted one request at a time and only their raw POST
        # data was kept: what it points to can have changed since, so it is
        # validated once more before anything is generated.
        form_dict = {
            step_name: self.get_form_for_step(step_name)
            for step_name in self.get_form_list()
        }
        for step_name, step_form in form_dict.items():
            if not step_form.is_valid():
                return self.render_revalidation_failure(step_name, step_form, **kwargs)
        response = self.done(form_dict.values(), form_dict=form_dict, **kwargs)
        self.storage.reset()
        return response

    def get_merged_cleaned_data(self, form_dict) -> dict:
        """Every step's cleaned_data, merged in flow order: later steps win."""
        merged_data = {}
        for step_form in form_dict.values():
            merged_data.update(step_form.cleaned_data)
        return merged_data


TEMPLATES = "gsl_notification/generated_document/multiple_wizard/"
PROGRESS_TEMPLATE = TEMPLATES + "modal_export_progress.html"
# The launch step is the trigger button submission, from the projet list page:
# its form resolves the projets the run applies to, hence one per wizard. It is
# only ever rendered when that resolution fails.
ACCEPTED_LAUNCH = Step(
    name="launch",
    form_class=GenerateAcceptedDocumentsLaunchForm,
    template=TEMPLATES + "modal_launch.html",
)
REFUS_LAUNCH = Step(
    name="launch",
    form_class=GenerateRefusLettersLaunchForm,
    template=TEMPLATES + "modal_launch.html",
)
TYPE_SELECTION = Step(
    name="type_selection",
    form_class=GenerateDocumentsTypeSelectionForm,
    template=TEMPLATES + "modal_form_step.html",
    title="Types de document",
)
MODELE_SELECTION = Step(
    name="modele_selection",
    form_class=GenerateDocumentsModeleSelectionForm,
    template=TEMPLATES + "modal_modele_selection.html",
    title="Choix des modèles",
    form_kwargs=("document_type", "programmation_projets"),
)
FORMAT = Step(
    name="format",
    form_class=GenerateDocumentsFormatForm,
    template=TEMPLATES + "modal_form_step.html",
    title="Format d'export",
    form_kwargs=("document_type",),
)
CREATE = Step(
    name="create",
    form_class=GenerateDocumentsCreateForm,
    template=TEMPLATES + "modal_loading.html",
    title="Téléchargement",
    form_kwargs=("programmation_projets",),
    extra_context=("doc_count",),
)


@method_decorator(htmx_only, name="dispatch")
class BaseGenerateDocumentsWizard(HtmxModalWizardMixin, SessionWizardView):
    """
    Generates documents for several projets of a single dotation at once: pick
    the modeles, pick an export format, then hand an ExportJob over to celery
    and poll it until the archive can be downloaded.

    Subclasses declare their flow through STEPS, plus:
    - MODAL_TITLE, modal_id: modal identifiers,
    - MODAL_POST_URL_NAME, STATUS_URL_NAME: their own URL names, used by the
      shared templates (form actions, polling endpoint),
    - get_document_type(): the kind of documents the run generates.
    """

    STATUS_URL_NAME: str = ""

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("dotation") not in DOTATIONS:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    def get_storage_namespace(self):
        # One run per dotation, so DETR and DSIL don't collide.
        return self.kwargs["dotation"]

    def get_document_type(self) -> str:
        """The type of document this run generates. Subclasses implement."""
        raise NotImplementedError

    def get_selected_types(self) -> frozenset[str]:
        """The document types the run generates, one document each per projet."""
        return SELECTED_TYPES_BY_CHOICE[self.get_document_type()]

    def get_programmation_projets(self):
        launch_data = self.get_cleaned_data_for_step(self.steps.first) or {}
        return launch_data.get("ids") or []

    def get_doc_count(self) -> int:
        return len(self.get_programmation_projets()) * len(self.get_selected_types())

    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        kwargs.update(
            {
                "user": self.request.user,
                "dotation": self.kwargs["dotation"],
                "request": self.request,
            }
        )
        return kwargs

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context["dotation"] = self.kwargs["dotation"]
        return context

    def done(self, form_list, form_dict, **kwargs):
        merged_data = self.get_merged_cleaned_data(form_dict)

        programmation_projets = form_dict[CREATE.name].save(
            modeles=form_dict[MODELE_SELECTION.name].selected_modeles,
            overwrite_strategy=merged_data.get("overwrite_strategy"),
        )

        selected_types = self.get_selected_types()
        job = ExportJob.objects.create(
            created_by=self.request.user,
            pp_ids=[pp.pk for pp in programmation_projets],
            # attr_names is stored as JSON: selected_types is a frozenset, so
            # pin a deterministic order (lettre before arrêté before refus,
            # matching the display order elsewhere) rather than the set itself.
            attr_names=[
                document_type
                for document_type in DOCUMENT_TYPE_DISPLAY_ORDER
                if document_type in selected_types
            ],
            export_format=merged_data.get("export_format"),
            document_type=self.get_document_type(),
            with_qr_code=merged_data.get("with_qr_code"),
        )
        generate_export_task.apply_async(
            args=[str(job.pk)],
            priority=TASK_PRIORITY_NORMAL,
        )

        return render(
            self.request,
            PROGRESS_TEMPLATE,
            self.get_job_context(job, self.kwargs["dotation"]),
        )

    @classmethod
    def get_job_context(cls, job, dotation) -> dict:
        """Context of the templates rendered once the export job is queued —
        by done() first, then by this wizard's status view on every poll."""
        return {
            "job_id": str(job.pk),
            "job": job,
            "dotation": dotation,
            "modal_id": cls.modal_id,
            "modal_title": cls.MODAL_TITLE,
            "total_steps": cls.total_steps,
            "status_url_name": cls.STATUS_URL_NAME,
        }


class GenerateAcceptedDocumentsWizard(BaseGenerateDocumentsWizard):
    """Arrêtés and lettres de notification of accepted projets."""

    STEPS = (
        ACCEPTED_LAUNCH,
        TYPE_SELECTION,
        MODELE_SELECTION,
        FORMAT,
        CREATE,
    )

    MODAL_TITLE = "Générer les documents"
    modal_id = "generate-multiple-modal"
    MODAL_POST_URL_NAME = "gsl_notification:generate-documents-modal"
    STATUS_URL_NAME = "gsl_notification:generate-documents-status"

    def get_document_type(self):
        type_selection_data = self.get_cleaned_data_for_step(TYPE_SELECTION.name) or {}
        return type_selection_data.get("document_type")


class GenerateLettreRefusWizard(BaseGenerateDocumentsWizard):
    """
    Lettres de refus of refused or dismissed projets. No type selection step:
    there is only one type of document to generate.
    """

    STEPS = (
        REFUS_LAUNCH,
        replace(MODELE_SELECTION, title="Choix du modèle"),
        FORMAT,
        CREATE,
    )

    MODAL_TITLE = "Générer les lettres de refus ou de classement sans suite"
    modal_id = "generate-refus-modal"
    MODAL_POST_URL_NAME = "gsl_notification:generate-refus-documents-modal"
    STATUS_URL_NAME = "gsl_notification:generate-refus-documents-status"

    def get_document_type(self):
        return LETTRE_REFUS


@method_decorator(htmx_only, name="dispatch")
class BaseGenerateDocumentsStatusView(DetailView):
    """
    Polled every 2 s while an export job started by a BaseGenerateDocumentsWizard
    is running.

    Subclasses set WIZARD_CLASS, the paired wizard supplying the modal
    identifiers, and fetch the relations their documents are rendered from.
    """

    model = ExportJob
    pk_url_kwarg = "job_id"

    WIZARD_CLASS: type = None

    def get_queryset(self):
        return ExportJob.objects.filter(created_by=self.request.user)

    def get(self, request, dotation, **_):
        job = self.get_object()
        context = self.WIZARD_CLASS.get_job_context(job, dotation)

        if job.is_running:
            return render(request, PROGRESS_TEMPLATE, context)

        if job.status != ExportJob.STATUS_DONE:
            return render(request, TEMPLATES + "modal_export_error.html", context)

        export_format = job.export_format
        context.update(
            {
                "download_url": job.download_url,
                "doc_count": len(job.pp_ids) * len(job.attr_names),
                "is_export_one_pdf_all": export_format == EXPORT_FORMAT_ONE_PDF_ALL,
                "is_export_one_pdf_all_grouped": export_format
                == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
                "is_export_one_pdf_per_project": export_format
                == EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
                "refreshed_programmation_projets": self.get_refreshed_programmation_projets(
                    job.pp_ids
                ),
            }
        )
        response = render(request, TEMPLATES + "modal_success.html", context)
        return trigger_client_event(response, "documents-generated")

    def get_refreshed_programmation_projets(self, pp_ids):
        """The generated documents are rendered back into the projet list rows,
        in the order the job stored them."""
        by_pk = {pp.pk: pp for pp in self.get_programmation_projets(pp_ids)}
        return [by_pk[pk] for pk in pp_ids if pk in by_pk]

    def get_programmation_projets(self, pp_ids):
        """Subclasses fetch the relations their success template renders."""
        return ProgrammationProjet.objects.filter(pk__in=pp_ids)


class GenerateAcceptedDocumentsStatusView(BaseGenerateDocumentsStatusView):
    WIZARD_CLASS = GenerateAcceptedDocumentsWizard

    def get_programmation_projets(self, pp_ids):
        return (
            super()
            .get_programmation_projets(pp_ids)
            .select_related("arrete", "lettrenotification", "lettre_et_arrete_signes")
            .prefetch_related("annexes")
        )


class GenerateLettreRefusStatusView(BaseGenerateDocumentsStatusView):
    WIZARD_CLASS = GenerateLettreRefusWizard

    def get_programmation_projets(self, pp_ids):
        return super().get_programmation_projets(pp_ids).select_related("lettrerefus")
