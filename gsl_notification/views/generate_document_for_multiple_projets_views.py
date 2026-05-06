import io
import logging
import zipfile

from django.http import HttpResponse
from django.shortcuts import get_list_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.decorators.http import require_GET
from django_htmx.http import trigger_client_event
from formtools.wizard.views import SessionWizardView
from pikepdf import Pdf

from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_notification.forms import (
    ARRETE_ET_LETTRE,
    EXPORT_FORMAT_ONE_PDF_ALL,
    EXPORT_FORMAT_ONE_PDF_ALL_GROUPED,
    EXPORT_FORMAT_ONE_PDF_PER_DOC,
    EXPORT_FORMAT_ONE_PDF_PER_PROJECT,
    SELECTED_TYPES_BY_CHOICE,
    GenerateDocumentsCreateForm,
    GenerateDocumentsLaunchForm,
    GenerateDocumentsStep1Form,
    GenerateDocumentsStep2Form,
    GenerateDocumentsStep3Form,
)
from gsl_notification.utils import (
    generate_pdf_for_generated_document,
    get_programmation_projet_attribute,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import (
    ARRETE,
    DOTATIONS,
    LETTRE,
)

logger = logging.getLogger(__name__)


@require_GET
def download_documents(request, dotation, document_type):
    if dotation not in DOTATIONS:
        raise Http404(user_message="Dotation inconnue")
    selected_types = SELECTED_TYPES_BY_CHOICE.get(document_type)
    if selected_types is None:
        raise Http404(user_message="Type de document inconnu")

    types = [t for t in (LETTRE, ARRETE) if t in selected_types]
    attrs = [get_programmation_projet_attribute(t) for t in types]
    attr_select_related = [
        "dotation_projet",
        "dotation_projet__projet",
        "dotation_projet__projet__dossier_ds",
        "dotation_projet__projet__dossier_ds__ds_demandeur",
        *attrs,
        *(f"{a}__modele" for a in attrs),
    ]

    ids_str = request.GET.get("ids", "")
    ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
    if ids:
        programmation_projets = get_list_or_404(
            ProgrammationProjet.objects.visible_to_user(request.user).select_related(
                *attr_select_related
            ),
            id__in=ids,
            dotation_projet__dotation=dotation,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            dotation_projet__projet__notified_at=None,
        )
        if len(programmation_projets) < len(ids):
            raise Http404(
                user_message="Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation, ou hors de votre périmètre)."
            )
    else:
        filterset = ProgrammationProjetFilters(data=request.GET, request=request)
        programmation_projets = filterset.qs.can_generate_documents().select_related(
            *attr_select_related
        )

    export_format = request.GET.get("export_format", EXPORT_FORMAT_ONE_PDF_PER_DOC)

    if export_format == EXPORT_FORMAT_ONE_PDF_ALL:
        return _download_single_merged_pdf(programmation_projets, attrs, document_type)
    if export_format == EXPORT_FORMAT_ONE_PDF_PER_PROJECT:
        return _download_one_pdf_per_project(programmation_projets, attrs)
    if export_format == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED:
        return _download_grouped_merged_pdf(programmation_projets, attrs)

    return _download_one_pdf_per_doc(programmation_projets, attrs)


def _download_one_pdf_per_doc(programmation_projets, attrs):
    try:
        documents = [
            doc
            for attr in attrs
            for doc in (getattr(pp, attr) for pp in programmation_projets)
        ]
    except (
        ProgrammationProjet.lettre_notification.RelatedObjectDoesNotExist,
        ProgrammationProjet.arrete.RelatedObjectDoesNotExist,
    ):
        raise Http404(user_message="Un des projets n'a pas le document demandé.")

    if len(documents) == 1:
        document = documents[0]
        pdf_content = generate_pdf_for_generated_document(document)
        logger.info(f"#1 {document} généré")
        response = HttpResponse(pdf_content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{document.name}"'
        return response

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for i, document in enumerate(documents, start=1):
            pdf_content = generate_pdf_for_generated_document(document)
            zip_file.writestr(f"{document.name}", pdf_content)
            logger.info(f"#{i} {document} généré")
    zip_buffer.seek(0)
    date_str = timezone.now().strftime("%d-%m-%Y")
    zip_filename = f"export turgot {date_str}.zip"
    response = HttpResponse(zip_buffer, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response


def _download_single_merged_pdf(programmation_projets, attrs, document_type):
    pdf_bytes_list = []
    for pp in programmation_projets:
        for attr in attrs:
            pdf_bytes_list.append(
                generate_pdf_for_generated_document(getattr(pp, attr))
            )
    merged = _merge_pdfs_bytes(pdf_bytes_list)
    date_str = timezone.now().strftime("%d-%m-%Y")
    if document_type == ARRETE:
        doc_type_fr = "arrêté"
    elif document_type == ARRETE_ET_LETTRE:
        doc_type_fr = "lettres et arrêtés"
    else:
        doc_type_fr = "lettre"
    filename = f"export {doc_type_fr} turgot {date_str}.pdf"
    response = HttpResponse(merged, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _download_one_pdf_per_project(programmation_projets, attrs):
    if len(programmation_projets) == 1:
        pp = programmation_projets[0]
        pdf_bytes_list = []
        for attr in attrs:
            pdf_bytes_list.append(
                generate_pdf_for_generated_document(getattr(pp, attr))
            )
        merged = _merge_pdfs_bytes(pdf_bytes_list)
        date_str = timezone.now().strftime("%d-%m-%Y")
        ds_number = pp.dossier.ds_number
        raison_sociale = slugify(pp.dossier.ds_demandeur.raison_sociale)
        filename = f"lettre et arrêté - {ds_number} - {raison_sociale} - {date_str}.pdf"
        response = HttpResponse(merged, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    date_str = timezone.now().strftime("%d-%m-%Y")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for pp in programmation_projets:
            project_pdfs = [
                generate_pdf_for_generated_document(getattr(pp, attr)) for attr in attrs
            ]
            merged = _merge_pdfs_bytes(project_pdfs)
            ds_number = pp.dossier.ds_number
            raison_sociale = slugify(pp.dossier.ds_demandeur.raison_sociale)
            filename = f"lettre et arrêté - {ds_number} - {raison_sociale}.pdf"
            zip_file.writestr(filename, merged)
    zip_buffer.seek(0)
    zip_filename = f"export turgot {date_str}.zip"
    response = HttpResponse(zip_buffer, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response


def _download_grouped_merged_pdf(programmation_projets, attrs):
    pdf_bytes_list = []
    for pp in programmation_projets:
        for attr in attrs:
            pdf_bytes_list.append(
                generate_pdf_for_generated_document(getattr(pp, attr))
            )
    merged = _merge_pdfs_bytes(pdf_bytes_list)
    date_str = timezone.now().strftime("%d-%m-%Y")
    filename = f"export turgot {date_str}.pdf"
    response = HttpResponse(merged, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _merge_pdfs_bytes(pdf_bytes_list: list[bytes]) -> bytes:
    pdf = Pdf.new()
    for pdf_bytes in pdf_bytes_list:
        src = Pdf.open(io.BytesIO(pdf_bytes))
        pdf.pages.extend(src.pages)
    output = io.BytesIO()
    pdf.save(output)
    output.seek(0)
    return output.read()


@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsWizard(SessionWizardView):
    LAUNCH_STEP = "launch"
    STEP1 = "step1"  # type de document
    STEP2 = "step2"  # choix des modèles + stratégie
    STEP3 = "step3"  # format d'export
    STEP4 = "step4"  # création (no-op form, déclenché par render_done)

    TEMPLATE_BASE = "gsl_notification/generated_document/multiple/"
    SUCCESS_TEMPLATE = TEMPLATE_BASE + "modal_success_body.html"

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
        response = self.done(form_dict.values(), form_dict=form_dict, **kwargs)
        self.storage.reset()
        return response

    def done(self, form_list, form_dict, **kwargs):
        form = form_dict[self.STEP4]
        step2_data = self.get_cleaned_data_for_step(self.STEP2) or {}
        step3_data = self.get_cleaned_data_for_step(self.STEP3) or {}
        export_format = step3_data.get("export_format")
        refreshed = form.save(
            modele_arrete=step2_data.get("modele_arrete_id"),
            modele_lettre=step2_data.get("modele_lettre_id"),
            overwrite_strategy=step2_data.get("overwrite_strategy"),
        )
        download_url = reverse(
            "gsl_notification:download-documents",
            kwargs={
                "dotation": self.kwargs["dotation"],
                "document_type": form.document_type,
            },
            query={
                "ids": ",".join(str(pp.id) for pp in form.programmation_projets),
                "export_format": export_format,
            },
        )
        context = {
            "modal_id": self.modal_id,
            "dotation": self.kwargs["dotation"],
            "form": form,
            "download_url": download_url,
            "doc_count": len(form.programmation_projets) * len(form.selected_types),
            "is_export_one_pdf_all": export_format == EXPORT_FORMAT_ONE_PDF_ALL,
            "is_export_one_pdf_all_grouped": (
                export_format == EXPORT_FORMAT_ONE_PDF_ALL_GROUPED
            ),
            "is_export_one_pdf_per_project": (
                export_format == EXPORT_FORMAT_ONE_PDF_PER_PROJECT
            ),
            "refreshed_programmation_projets": refreshed,
        }
        return render(self.request, self.SUCCESS_TEMPLATE, context)
