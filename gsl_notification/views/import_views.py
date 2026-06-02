import uuid
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, FormView, TemplateView

from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_IMPORT_DOCUMENT,
    MATOMO_CATEGORY_DOCUMENT,
)
from gsl_core.view_mixins import OpenHtmxModalMixin
from gsl_notification.forms import ImportJobStartForm, PresignedUploadForm
from gsl_notification.models import DocumentImportJob
from gsl_notification.utils import get_s3_client
from gsl_projet.constants import DOTATIONS

IMPORT_MODAL_ID = "import-modal"

TEMPLATE_BASE = "gsl_notification/import/"

# A hard worker kill (OOM/SIGKILL) bypasses the task's `finally` and leaves the
# job RUNNING forever, so the browser would poll indefinitely. Past this cutoff
# we render the summary with a stale warning instead. It matches the presigned
# POST's ExpiresIn=3600, which generously outlasts any real import.
_STALE_JOB_CUTOFF = timedelta(hours=1)


def _max_import_bytes() -> int:
    return settings.MAX_IMPORT_TOTAL_SIZE_IN_MO * 1024 * 1024


@method_decorator(htmx_only, name="dispatch")
class ImportDocumentsModalView(OpenHtmxModalMixin, TemplateView):
    """
    Opens the import wizard: renders the step-1 dropzone body, swapped into the
    modal shell already present on the page, and triggers the DSFR modal-open
    click. GET because opening the modal is side-effect-free and carries no
    project selection (QR matching is global).
    """

    template_name = TEMPLATE_BASE + "modal_upload_body.html"
    modal_id = IMPORT_MODAL_ID

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("dotation") not in DOTATIONS:
            raise Http404(user_message="Dotation inconnue")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["dotation"] = self.kwargs["dotation"]
        context["max_import_size_in_mo"] = settings.MAX_IMPORT_TOTAL_SIZE_IN_MO
        return context


class PresignedUploadView(FormView):
    """
    Returns the parameters for a direct browser→S3 presigned POST so a scan can
    be uploaded without going through Django (Scalingo caps the request body).
    The policy conditions make S3 itself reject oversize or non-PDF uploads.
    """

    form_class = PresignedUploadForm
    http_method_names = ["post"]

    def form_valid(self, form):
        sanitized = form.cleaned_data["filename"]

        key = f"{DocumentImportJob.TEMP_S3_PREFIX}{uuid.uuid4()}/{sanitized}"
        # Per-file S3 cap is intentionally the cumulative cap: bulk scans are the
        # feature's purpose and a single multi-dossier PDF can be large. The
        # browser-side cumulative check bounds a whole batch; the bucket
        # lifecycle rule (see configure_s3_bucket) backstops orphaned uploads.
        max_bytes = _max_import_bytes()

        presigned = get_s3_client().generate_presigned_post(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key,
            Fields={"Content-Type": "application/pdf"},
            Conditions=[
                ["content-length-range", 0, max_bytes],
                ["starts-with", "$Content-Type", "application/pdf"],
            ],
            ExpiresIn=3600,
        )
        return JsonResponse(
            {"url": presigned["url"], "fields": presigned["fields"], "key": key}
        )

    def form_invalid(self, form):
        return JsonResponse({"error": form.errors["filename"][0]}, status=400)


@method_decorator(htmx_only, name="dispatch")
class ImportJobStartView(FormView):
    """
    Creates a DocumentImportJob for the uploaded S3 keys, enqueues the Celery
    task, and renders the progress partial. Subsequent updates come from
    `ImportJobProgressView` polling.
    """

    form_class = ImportJobStartForm
    http_method_names = ["post"]

    def form_valid(self, form):
        job = form.save(self.request.user)
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_DOCUMENT,
            MATOMO_ACTION_IMPORT_DOCUMENT,
            f"import:{len(job.s3_keys)}",
        )
        return render(
            self.request,
            TEMPLATE_BASE + "_import_progress_partial.html",
            {"job": job, "modal_id": IMPORT_MODAL_ID},
        )

    def form_invalid(self, form):
        # Errors here mean client tampering or a bug, not user-correctable input.
        raise Http404(user_message=next(iter(form.errors.values()))[0])


@method_decorator(htmx_only, name="dispatch")
class ImportJobProgressView(DetailView):
    """
    Polled every 2 s while the job is running. Returns the progress partial
    (which keeps polling) while running, and the summary partial (no poll) once
    done — same root id so the HTMX outerHTML swap is clean. Scoped to the
    requesting user's own jobs.
    """

    model = DocumentImportJob
    context_object_name = "job"

    def get_queryset(self):
        return DocumentImportJob.objects.filter(created_by=self.request.user)

    def _is_stale(self) -> bool:
        return (
            self.object.is_running
            and self.object.created_at < timezone.now() - _STALE_JOB_CUTOFF
        )

    def get_template_names(self):
        if self.object.is_running and not self._is_stale():
            return [TEMPLATE_BASE + "_import_progress_partial.html"]
        return [TEMPLATE_BASE + "modal_summary_body.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modal_id"] = IMPORT_MODAL_ID
        context["stale"] = self._is_stale()
        return context
