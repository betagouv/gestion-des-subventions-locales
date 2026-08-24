from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.csp import CSP
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView, DetailView, FormView, UpdateView
from django_htmx.http import HttpResponseClientRefresh

from gsl.utils.csp import csp_update
from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_ENVOI_DN,
    MATOMO_CATEGORY_NOTIFICATION,
)
from gsl_core.templatetags.fragment_tags import register_fragment_tag
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_historique.models import ProjetAction
from gsl_notification.forms import (
    GENERATED_DOCUMENT_TO_FORM,
    ChoixModeleForm,
    GenerateDotationsDocumentsForm,
    NotificationMessageForm,
)
from gsl_notification.models import (
    GENERATED_DOCUMENTS,
    MODELES,
    UPLOADED_DOCUMENTS,
    GeneratedDocument,
)
from gsl_notification.utils import (
    generate_pdf_for_generated_document,
    get_modele_perimetres,
    log_generated_document_action,
    merge_generated_documents_into_pdf,
    replace_mentions_in_html,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import Projet
from gsl_projet.utils.projet_page import get_projet_go_back_context
from gsl_projet.views import BaseProjetDetailView

# Views for listing notification documents on a programmationProjet, -------------------
# in various contexts


class NotificationDocumentsView(BaseProjetDetailView):
    template_name = "gsl_notification/tab_simulation_projet/tab_notifications.html"

    def get_queryset(self):
        return (
            Projet.objects.active()
            .for_user(self.request.user)
            .with_at_least_one_treated_dotation()
        )

    def get_context_data(self, **kwargs):
        title = self.object.dossier_ds.projet_intitule
        return super().get_context_data(
            **{
                "dossier": self.object.dossier_ds,
                "dotation_projets": self.object.dotationprojet_set.all(),
                "generated_documents": self.object.generated_documents,
                "imported_documents": self.object.imported_documents,
                "title": title,
                **get_projet_go_back_context(self.request),
            }
        )


@register_fragment_tag("generate_documents_form")
@method_decorator(htmx_only, name="dispatch")
class GenerateDocumentsFormView(UpdateView):
    """
    HTMX endpoint backing the "1 - Générer" block of the notifications tab.
    Always re-renders the whole #generate-documents-block, which is also
    its own hx-target, so the response can swap itself in place.

    GenerateAcceptedDotationsDocumentsForm is a plain Form (projet/user
    passed as custom kwargs), not a ModelForm, so ModelFormMixin's
    get_form_kwargs (which injects `instance`) must be stripped before
    calling the form.
    """

    model = Projet
    form_class = GenerateDotationsDocumentsForm
    template_name = "includes/_generate_documents_form.html"
    pk_url_kwarg = "projet_id"
    context_object_name = "projet"

    def get_queryset(self):
        return (
            Projet.objects.active()
            .for_user(self.request.user)
            .with_at_least_one_treated_dotation()
            .filter(notified_at__isnull=True)
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop("instance", None)
        kwargs["projet"] = self.object
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        return HttpResponseClientRefresh()

    def form_invalid(self, form):
        form.set_autofocus_on_first_error()  # TODO systemize this on form_invalid ??
        return super().form_invalid(form)


NOTIFICATION_RESULT_TO_MATOMO_ACTION = {
    PROJET_STATUS_ACCEPTED: "accepte",
    PROJET_STATUS_REFUSED: "refuse",
    PROJET_STATUS_DISMISSED: "classe_sans_suite",
}


@register_fragment_tag("notification_message_form")
@method_decorator(htmx_only, name="dispatch")
class NotificationMessageFormView(UpdateView):
    """
    HTMX endpoint backing the "3 - Notifier" block of the notifications tab.
    Always re-renders the whole #notification-message-block, which is also
    its own hx-target, so the response can swap itself in place. On success,
    it also OOB-swaps the "4 - Notifié" block so both reflect the new
    notified_at without a full page refresh.
    """

    form_class = NotificationMessageForm
    template_name = "includes/_notification_message_form.html"
    pk_url_kwarg = "projet_id"
    context_object_name = "projet"
    model = Projet

    def get_queryset(self):
        return Projet.objects.active().for_user(self.request.user).to_notify()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_instructor"] = self.object.dossier_ds.is_instructeur(
            self.request.user
        )
        context["dotation_projets_without_signed_document"] = list(
            self.object.dotationprojet_set.without_signed_document()
        )
        return context

    def form_valid(self, form):
        try:
            form.save(user=self.request.user)
        except DsServiceException as e:
            form.add_error(
                None,
                f"Une erreur est survenue lors de l'envoi de la notification. {str(e)}",
            )
            return self.form_invalid(form)

        matomo_action_value = NOTIFICATION_RESULT_TO_MATOMO_ACTION[self.object.status]
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_NOTIFICATION,
            MATOMO_ACTION_ENVOI_DN,
            matomo_action_value,
        )

        notification_message_block = render_to_string(
            self.template_name, self.get_context_data(), request=self.request
        )

        oob_context = {"projet": self.object, "hx_swap_oob": "true"}
        notified_block = render_to_string(
            "includes/_notified_block.html", oob_context, request=self.request
        )
        projet_actions_block = render_to_string(
            "includes/projet_detail/_projet_actions.html",
            {
                **oob_context,
                "next_url": self.request.headers.get(
                    "HX-Current-URL", self.request.path
                ),
            },
            request=self.request,
        )
        dotation_status_cards_block = render_to_string(
            "includes/projet_detail/_dotation_status_cards.html",
            {
                **oob_context,
                "dotation_projets": self.object.dotationprojet_set.order_by(
                    "dotation"
                ),
            },
            request=self.request,
        )
        return HttpResponse(
            notification_message_block
            + notified_block
            + projet_actions_block
            + dotation_status_cards_block
        )


# Edition form for arrêté --------------------------------------------------------------


class SelectModeleView(FormView):
    template_name = "gsl_notification/generated_document/select_modele.html"
    form_class = ChoixModeleForm

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.document_type = kwargs["document_type"]
        try:
            self.modele_class = MODELES[self.document_type]
        except KeyError:
            raise Http404(user_message="Le type de document sélectionné n'existe pas.")
        self.programmation_projet = get_object_or_404(
            ProgrammationProjet.objects.active().visible_to_user(request.user),
            dotation_projet__projet_id=kwargs["projet_id"],
            enveloppe__dotation=kwargs["dotation"],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        dotation = self.programmation_projet.dotation
        perimetres = get_modele_perimetres(dotation, self.request.user.perimetre)
        kwargs["queryset"] = self.modele_class.objects.filter(
            dotation=dotation, perimetre__in=perimetres
        )
        if hasattr(self.programmation_projet, self.document_type):
            kwargs["initial"] = {
                "modele": getattr(
                    self.programmation_projet, self.document_type
                ).modele_id
            }
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
            projet=self.programmation_projet.projet,
            dossier=self.programmation_projet.projet.dossier_ds,
            programmation_projet=self.programmation_projet,
            dotation=self.programmation_projet.dotation,
            document_type=self.document_type,
            modele_label=self.modele_class.verbose_name(),
            page_title=f"Modification de {self.modele_class.article_name}",
            page_step_title=f"1 - Choix du modèle de {self.modele_class.article_name}",
            cancel_link=reverse(
                "gsl_notification:documents", args=[self.kwargs["projet_id"]]
            ),
        )


@method_decorator(
    csp_update({"style-src": [CSP.SELF, CSP.UNSAFE_INLINE]}), name="dispatch"
)
class ChangeDocumentView(UpdateView):
    template_name = "gsl_notification/generated_document/change_document.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.document_type = kwargs["document_type"]
        try:
            self.modele_class = MODELES[self.document_type]
            self.form_class = GENERATED_DOCUMENT_TO_FORM[self.document_type]
        except KeyError:
            raise Http404(user_message="Le type de document sélectionné n'existe pas.")

    def get_object(self, queryset=None):
        self.programmation_projet = get_object_or_404(
            ProgrammationProjet.objects.active().visible_to_user(self.request.user),
            dotation_projet__projet_id=self.kwargs["projet_id"],
            enveloppe__dotation=self.kwargs["dotation"],
        )
        if not hasattr(self.programmation_projet, self.document_type):
            raise Http404(user_message="Il n'y a pas de document à modifier.")
        document = getattr(self.programmation_projet, self.document_type)
        self.modele = document.modele

        modele_id = self.request.GET.get("modele_id")
        if modele_id:
            dotation = self.programmation_projet.dotation
            perimetres = get_modele_perimetres(dotation, self.request.user.perimetre)
            self.modele = get_object_or_404(
                self.modele_class,
                id=modele_id,
                dotation=dotation,
                perimetre__in=perimetres,
            )
            document.content = replace_mentions_in_html(
                self.modele.content, self.programmation_projet
            )
        return document

    def form_valid(self, form):
        response = super().form_valid(form)
        _add_success_message(self.request, self.object)
        log_generated_document_action(
            self.request.user,
            self.programmation_projet,
            self.object.__class__,
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
        context["page_title"] = f"Modification de {self.modele_class.article_name}"
        context["page_step_title"] = (
            f"1 - Choix du modèle de {self.modele_class.article_name}"
        )
        context["modele"] = self.modele
        context["document_type"] = self.document_type
        _enrich_context_for_create_or_get_arrete_view(
            context, self.programmation_projet, self.request
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
    context_object_name = "document"
    pk_url_kwarg = "document_id"

    def get_queryset(self):
        try:
            DOCUMENTS = {**GENERATED_DOCUMENTS, **UPLOADED_DOCUMENTS}
            document_class = DOCUMENTS[self.kwargs["document_type"]]
        except KeyError:
            raise Http404(user_message="Le type de document sélectionné n'existe pas.")

        return document_class.objects.filter(
            programmation_projet__dotation_projet__projet__in=Projet.objects.active().for_user(
                self.request.user
            )
        )

    def form_valid(self, form):
        pp = self.object.programmation_projet
        doc_class_name = self.object.__class__._meta.verbose_name
        action_type = (
            ProjetAction.TYPE_DOC_UPLOAD_DELETED
            if hasattr(self.object, "file")
            else ProjetAction.TYPE_DOC_DELETED
        )
        ProjetAction.objects.create(
            projet=pp.dotation_projet.projet,
            action_type=action_type,
            actor=self.request.user,
            source=ProjetAction.SOURCE_TURGOT,
            dotation=pp.dotation_projet.dotation,
            document_name=doc_class_name,
        )
        messages.success(self.request, "Le document a bien été supprimé.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": self.object.programmation_projet.projet.id},
        )


# View and Download views -----------------------------------------------------------------------


class PrintDocumentView(DetailView):
    model = GeneratedDocument
    pk_url_kwarg = "document_id"

    # show pdf in-line (False) or as a download dialog (True)
    pdf_attachment = False

    def get_queryset(self):
        self.document_type = self.kwargs["document_type"]
        try:
            document_class = MODELES[self.document_type].generated_document_class
            if document_class is None:
                raise ValueError("Type inconnu")
        except (ValueError, KeyError):
            raise Http404(user_message="Le type de document sélectionné n'existe pas.")

        return document_class.objects.filter(
            programmation_projet__dotation_projet__projet__in=Projet.objects.active().for_user(
                self.request.user
            )
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


def _enrich_context_for_create_or_get_arrete_view(
    context, programmation_projet, request
):
    context.update(
        {
            "programmation_projet": programmation_projet,
            "projet": programmation_projet.projet,
            "dossier": programmation_projet.projet.dossier_ds,
            "current_tab": "notifications",
        }
    )
