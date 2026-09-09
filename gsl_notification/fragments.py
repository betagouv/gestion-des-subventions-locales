import logging

from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.template.loader import render_to_string
from django_htmx.http import HttpResponseClientRefresh
from pikepdf import PdfError
from pypdfium2 import PdfiumError

from gsl.historique.models import ProjetAction
from gsl.projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl.projet.fragments import BaseProjetFragment, ProjetActionsFragment
from gsl.projet.models import Projet
from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_ENVOI_DN,
    MATOMO_ACTION_IMPORT_DOCUMENT,
    MATOMO_CATEGORY_DOCUMENT,
    MATOMO_CATEGORY_NOTIFICATION,
)
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_notification.forms import (
    GenerateDotationsDocumentsForm,
    ManualDocumentAttachForm,
    NotificationMessageForm,
    UploadedDocumentAnalyzeForm,
)
from gsl_notification.models import DocumentImportJob
from gsl_notification.qr.reattach import (
    DocumentMatched,
    MatchFailed,
    PageDecoded,
    extract_documents,
    replace_documents,
)
from gsl_programmation.models import ProgrammationProjet

logger = logging.getLogger(__name__)

NOTIFICATION_RESULT_TO_MATOMO_ACTION = {
    PROJET_STATUS_ACCEPTED: "accepte",
    PROJET_STATUS_REFUSED: "refuse",
    PROJET_STATUS_DISMISSED: "classe_sans_suite",
}

UPLOAD_MODAL_ID = "upload-document-modal"
IMPORT_TEMPLATE_BASE = "gsl_notification/modal/projet_import/"


class NotifiedFragment(BaseProjetFragment):
    name = "notified"
    template_name = (
        "gsl_notification/tab_simulation_projet/tab_notifications.html#notified"
    )

    def get_context(self):
        return {
            **super().get_context(),
            "notifications": self.object.actions.filter(
                action_type=ProjetAction.TYPE_NOTIFIED
            )
            .select_related("actor")
            .order_by("created_at"),
        }


class GenerateDocumentsFragment(BaseProjetFragment):
    name = "generate_documents"
    route_params = "<int:pk>"
    template_name = "includes/_generate_documents_form.html"
    form_class = GenerateDotationsDocumentsForm

    @classmethod
    def get_queryset(cls, request):
        return (
            Projet.objects.active()
            .for_user(request.user)
            .with_at_least_one_treated_dotation()
            .filter(notified_at__isnull=True)
        )

    def get_form(self, data=None):
        return self.form_class(projet=self.object, user=self.request.user, data=data)

    def on_valid(self):
        self.form.save()
        return HttpResponseClientRefresh()


class NotificationMessageFragment(BaseProjetFragment):
    name = "notification_message"
    route_params = "<int:pk>"
    template_name = "includes/_notification_message_form.html"
    form_class = NotificationMessageForm
    oob_fragments = (NotifiedFragment, ProjetActionsFragment, GenerateDocumentsFragment)

    @classmethod
    def get_queryset(cls, request):
        return Projet.objects.active().for_user(request.user).to_notify()

    def get_context(self):
        return {
            **super().get_context(),
            "is_instructor": self.object.dossier_ds.is_instructeur(self.request.user),
            "dotation_projets_without_signed_document": list(
                self.object.dotationprojet_set.without_signed_document()
            ),
        }

    def on_valid(self):
        try:
            self.form.save(user=self.request.user)
        except DsServiceException as e:
            self.form.add_error(
                None,
                f"Une erreur est survenue lors de l'envoi de la notification. {e}",
            )
            return self.on_invalid()

        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_NOTIFICATION,
            MATOMO_ACTION_ENVOI_DN,
            NOTIFICATION_RESULT_TO_MATOMO_ACTION[self.object.status],
        )
        return self.render_valid()


class ImportedDocumentsFragment(BaseProjetFragment):
    name = "imported_documents"
    template_name = (
        "gsl_notification/tab_simulation_projet/"
        "tab_notifications.html#imported_documents"
    )

    def get_context(self):
        return {
            **super().get_context(),
            "imported_documents": self.object.imported_documents,
        }


class BaseImportStepFragment(BaseProjetFragment):
    """Base fragment of the per-projet import modal.

    Steps render one another — the file decides which comes next — so a step
    returns another fragment's `render()` rather than only its own.
    """

    # An imported document lands in the table, and a signed lettre unblocks the
    # "Notifier" button.
    oob_fragments = (ImportedDocumentsFragment, NotificationMessageFragment)

    @classmethod
    def get_queryset(cls, request):
        return (
            Projet.objects.active()
            .for_user(request.user)
            .to_notify()
            .with_at_least_one_treated_dotation()
        )

    def get_context(self):
        return {
            **super().get_context(),
            "modal_id": UPLOAD_MODAL_ID,
            "modal_title": "Importer un document",
        }

    def render_summary(self, documents, unreadable_pages=()):
        """The end of the flow: a plain template, since it answers another
        step's URL and nothing ever renders it on its own."""
        html = render_to_string(
            IMPORT_TEMPLATE_BASE + "summary_step.html",
            {
                **self.get_context(),
                "documents": documents,
                "unreadable_pages": sorted(unreadable_pages),
            },
            request=self.request,
        )
        return HttpResponse(html + self.render_oob())

    def _log_import(self, document):
        dotation = document.programmation_projet.dotation
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_DOCUMENT,
            MATOMO_ACTION_IMPORT_DOCUMENT,
            dotation,
        )
        ProjetAction.objects.create(
            projet=self.object,
            action_type=ProjetAction.TYPE_DOC_UPLOADED,
            actor=self.request.user,
            source=ProjetAction.SOURCE_TURGOT,
            dotation=dotation,
            document_name=type(document)._meta.verbose_name,
        )


class UploadedDocumentAnalyzeFragment(BaseImportStepFragment):
    """The file itself. A scan of a generated document carries a GSL QR code on
    every page, naming the dossier, the dotation and the document type — enough
    to attach it without asking anything. Only when that fails is the type
    asked for."""

    name = "upload_document_analyze"
    route_params = "<int:pk>"
    template_name = IMPORT_TEMPLATE_BASE + "upload_step.html"
    form_class = UploadedDocumentAnalyzeForm

    def get_form(self, data=None):
        files = self.request.FILES if data is not None else None
        return self.form_class(data=data, files=files)

    def on_get(self):
        """The dialog fetches this step on every opening, so a step left in
        error is never what the agent comes back to."""
        return HttpResponse(self.render())

    def on_valid(self):
        uploaded_file = self.form.cleaned_data["file"]
        if not uploaded_file.name.lower().endswith(".pdf"):
            # Only PDFs can carry a QR code; images go straight to the choice.
            return self._ask_for_the_type(uploaded_file)

        attached, failures, unreadable_pages = self._reattach(
            uploaded_file, remove_qr_code=self.form.cleaned_data["remove_qr_code"]
        )
        if attached:
            return self.render_summary(attached, unreadable_pages)
        if failures:
            self.form.add_error("file", failures[0])
            return self.render_invalid()
        return self._ask_for_the_type(uploaded_file)

    def _ask_for_the_type(self, uploaded_file):
        """No QR code told us what this file is — ask.

        The file waits under the temporary prefix, whose lifecycle rule sweeps
        it away if the agent never answers.
        """
        key = default_storage.save(
            DocumentImportJob.temp_s3_key(uploaded_file.name), uploaded_file
        )
        return self.respond_with(ManualDocumentAttachFragment, key=key)

    def _reattach(self, uploaded_file, remove_qr_code: bool):
        documents, failures, unreadable_pages = [], [], []
        try:
            for event in extract_documents(
                [uploaded_file],
                ProgrammationProjet.objects.visible_to_user(self.request.user),
            ):
                if isinstance(event, DocumentMatched):
                    documents.append(event.document)
                elif isinstance(event, MatchFailed):
                    failures.append(self._describe(event.declared, event.error))
                elif isinstance(event, PageDecoded) and not event.qr_found:
                    unreadable_pages.append(event.scan_page)
        except (PdfError, PdfiumError):
            # A PDF we cannot even parse carries no readable QR either: fall
            # through to the choice step rather than fail the whole import.
            # The file itself is still storable, as it was before this modal.
            logger.info("Import : PDF illisible, bascule sur le choix manuel")
            return [], [], []

        elsewhere = [
            document
            for document in documents
            if document.declared.ds_number != self.object.dossier_ds.ds_number
        ]
        if elsewhere:
            # Nothing has been written yet, so the whole file can be turned
            # down rather than half of it stored under this projet.
            return [], [self._describe(elsewhere[0].declared)], unreadable_pages

        stored = replace_documents(
            documents, [uploaded_file], self.request.user, remove_qr_code
        )
        attached = [
            document.declared.target_model.objects.get(
                programmation_projet_id=document.programmation_projet_id
            )
            for document in stored
        ]
        for document in attached:
            self._log_import(document)
        return attached, failures, unreadable_pages

    def _describe(self, declared, fallback=None):
        if declared.ds_number != self.object.dossier_ds.ds_number:
            return (
                f"Ce document porte le QR code du dossier n° {declared.ds_number}, "
                "il ne correspond pas à ce projet."
            )
        return fallback


class ManualDocumentAttachFragment(BaseImportStepFragment):
    """The file carried no usable QR code: the agent names the dotation and the
    document type, and the browser posts back the key it is parked under."""

    name = "manual_document_attach"
    route_params = "<int:pk>"
    template_name = IMPORT_TEMPLATE_BASE + "choice_step.html"
    form_class = ManualDocumentAttachForm

    def __init__(self, request, obj, key=None):
        super().__init__(request, obj)
        self.key = key

    def get_form(self, data=None):
        return self.form_class(data=data, projet=self.object, initial={"key": self.key})

    def on_valid(self):
        document = self.form.save(self.request.user)
        self._log_import(document)
        return self.render_summary([document])
