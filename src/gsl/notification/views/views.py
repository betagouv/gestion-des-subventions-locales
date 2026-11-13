from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.csp import CSP
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView, DetailView, FormView, UpdateView

from gsl.core.exceptions import Http404
from gsl.historique.models import ProjetAction
from gsl.notification.forms.update_doc import ChoixModeleForm, GeneratedDocumentForm
from gsl.notification.models import GeneratedDocument, ModeleDocument, UploadedDocument
from gsl.notification.utils import (
    generate_pdf_for_generated_document,
    get_modele_perimetres,
    log_generated_document_action,
    merge_generated_documents_into_pdf,
    replace_mentions_in_html,
)
from gsl.projet.models import EnveloppeProjet, Projet
from gsl.projet.views import BaseProjetDetailView
from gsl.utils.csp import csp_update

# Views for listing notification documents on a EnveloppeProjet, ------------------------
# in various contexts


class NotificationDocumentsView(BaseProjetDetailView):
    template_name = "gsl_notification/tab_notifications.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **{"generated_documents": self.object.generated_documents}
        )


# Edition form for arrêté --------------------------------------------------------------


class SelectModeleView(FormView):
    template_name = "gsl_notification/generated_document/select_modele.html"
    form_class = ChoixModeleForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.document_type = kwargs["document_type"]
        self.enveloppe_projet = get_object_or_404(
            EnveloppeProjet.objects.programmees()
            .active()
            .visible_to_user(request.user)
            .for_dotation(kwargs["dotation"]),
            projet_id=kwargs["projet_id"],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        dotation = self.enveloppe_projet.dotation
        perimetres = get_modele_perimetres(dotation, self.request.user.perimetre)
        kwargs["queryset"] = ModeleDocument.objects.filter(
            type=self.document_type, dotation=dotation, perimetre__in=perimetres
        )
        document = self.enveloppe_projet.generated_document(self.document_type)
        if document:
            kwargs["initial"] = {"modele": document.modele_id}
        return kwargs

    def form_valid(self, form):
        return redirect(
            reverse(
                "notification:modifier-document",
                kwargs={
                    "projet_id": self.kwargs["projet_id"],
                    "dotation": self.kwargs["dotation"],
                    "document_type": self.document_type,
                },
                query={"modele_id": form.cleaned_data["modele"].id},
            )
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            **kwargs,
            projet=self.enveloppe_projet.projet,
            dossier=self.enveloppe_projet.projet.dossier_ds,
            enveloppe_projet=self.enveloppe_projet,
            dotation=self.enveloppe_projet.dotation,
            document_type=self.document_type,
            modele_label=self.document_type.modele_verbose_name,
            page_title=f"Modification de {self.document_type.article_name}",
            page_step_title=(
                f"1 - Choix du modèle de {self.document_type.article_name}"
            ),
            cancel_link=reverse(
                "gsl_notification:documents", args=[self.kwargs["projet_id"]]
            ),
        )


@method_decorator(
    csp_update({"style-src": [CSP.SELF, CSP.UNSAFE_INLINE]}), name="dispatch"
)
class ChangeDocumentView(UpdateView):
    template_name = "gsl_notification/generated_document/change_document.html"
    form_class = GeneratedDocumentForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.document_type = kwargs["document_type"]

    def get_object(self, queryset=None):
        self.enveloppe_projet = get_object_or_404(
            EnveloppeProjet.objects.programmees()
            .active()
            .visible_to_user(self.request.user)
            .for_dotation(self.kwargs["dotation"]),
            projet_id=self.kwargs["projet_id"],
        )
        document = self.enveloppe_projet.generated_document(self.document_type)
        if document is None:
            raise Http404(user_message="Il n'y a pas de document à modifier.")
        self.modele = document.modele

        modele_id = self.request.GET.get("modele_id")
        if modele_id:
            dotation = self.enveloppe_projet.dotation
            perimetres = get_modele_perimetres(dotation, self.request.user.perimetre)
            self.modele = get_object_or_404(
                ModeleDocument,
                id=modele_id,
                type=self.document_type,
                dotation=dotation,
                perimetre__in=perimetres,
            )
            document.content = replace_mentions_in_html(
                self.modele.content, self.enveloppe_projet
            )
        return document

    def form_valid(self, form):
        response = super().form_valid(form)
        _add_success_message(self.request, self.object)
        log_generated_document_action(
            self.request.user,
            self.enveloppe_projet,
            self.object,
            is_creating=False,
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Erreur dans le formulaire")
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": self.kwargs["projet_id"]},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["arrete_form"] = context["form"]
        context["arrete_initial_content"] = mark_safe(self.object.content)
        context["page_title"] = f"Modification de {self.document_type.article_name}"
        context["page_step_title"] = (
            f"1 - Choix du modèle de {self.document_type.article_name}"
        )
        context["modele"] = self.modele
        context["document_type"] = self.document_type
        _enrich_context_for_create_or_get_arrete_view(
            context, self.enveloppe_projet, self.request
        )
        return context


def _add_success_message(request, document):
    article = document.article_name
    type_and_article = article[0].upper() + article[1:]
    accord = "e" if article.startswith("la ") else ""
    messages.info(
        request,
        f"{type_and_article} “{document.name}” a bien été modifié{accord}.",
    )


# Suppression d'arrêté -----------------------------------------------------------------


@method_decorator(require_POST, name="dispatch")
class DeleteDocumentView(DeleteView):
    action_type: str
    context_object_name = "document"
    pk_url_kwarg = "document_id"

    def get_queryset(self):
        return self.model.objects.filter(
            enveloppe_projet__projet__in=Projet.objects.active().for_user(
                self.request.user
            ),
        )

    def form_valid(self, form):
        enveloppe_projet = self.object.enveloppe_projet
        ProjetAction.objects.create(
            projet=enveloppe_projet.projet,
            action_type=self.action_type,
            actor=self.request.user,
            source=ProjetAction.SOURCE_TURGOT,
            dotation=enveloppe_projet.dotation,
            document_name=self.object.verbose_name,
        )
        messages.success(self.request, "Le document a bien été supprimé.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": self.object.enveloppe_projet.projet.id},
        )


class DeleteGeneratedDocumentView(DeleteDocumentView):
    model = GeneratedDocument
    action_type = ProjetAction.TYPE_DOC_DELETED


class DeleteUploadedDocumentView(DeleteDocumentView):
    model = UploadedDocument
    action_type = ProjetAction.TYPE_DOC_UPLOAD_DELETED


# View and Download views -----------------------------------------------------------------------


class PrintDocumentView(DetailView):
    model = GeneratedDocument
    pk_url_kwarg = "document_id"

    # show pdf in-line (False) or as a download dialog (True)
    pdf_attachment = False

    def get_queryset(self):
        return GeneratedDocument.objects.filter(
            enveloppe_projet__projet__in=Projet.objects.active().for_user(
                self.request.user
            ),
        )

    def get(self, request, *args, **kwargs):
        document = self.get_object()
        pdf = generate_pdf_for_generated_document(
            document, with_qr_code=document.with_qr_code
        )
        disposition = "attachment" if self.pdf_attachment else "inline"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'{disposition}; filename="{document.name}"'
        return response


class DownloadDocumentView(PrintDocumentView):
    pdf_attachment = True


class DownloadMergedGeneratedDocumentsView(DetailView):
    """Merges every generated document of a projet (arrêté, lettre...) into a
    single PDF, in the same order as the documents table."""

    pk_url_kwarg = "projet_id"

    def get_queryset(self):
        return (
            Projet.objects.active()
            .for_user(self.request.user)
            .with_at_least_one_treated_dotation()
        )

    def get(self, request, *args, **kwargs):
        projet = self.get_object()
        documents = projet.generated_documents
        if not documents:
            raise Http404(user_message="Aucun document généré à télécharger.")
        pdf = merge_generated_documents_into_pdf(documents)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="Documents {projet.dossier_ds.name_for_document}.pdf"'
        )
        return response


def _enrich_context_for_create_or_get_arrete_view(context, enveloppe_projet, request):
    context.update(
        {
            "enveloppe_projet": enveloppe_projet,
            "projet": enveloppe_projet.projet,
            "dossier": enveloppe_projet.projet.dossier_ds,
            "current_tab": "notifications",
        }
    )
