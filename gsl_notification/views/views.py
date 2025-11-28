from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, UpdateView
from django_htmx.http import HttpResponseClientRedirect
from django_weasyprint import WeasyTemplateResponseMixin

from gsl_core.decorators import htmx_only
from gsl_core.view_mixins import OpenHtmxModalMixin
from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_notification.forms import NotificationMessageForm
from gsl_notification.models import (
    GeneratedDocument,
)
from gsl_notification.utils import (
    get_doc_title,
    get_document_class,
    get_form_class,
    get_modele_class,
    get_modele_perimetres,
    replace_mentions_in_html,
)
from gsl_notification.views.decorators import (
    document_visible_by_user,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    ARRETE,
    LETTRE,
    POSSIBLES_DOCUMENTS,
)
from gsl_projet.models import Projet

# Views for listing notification documents on a programmationProjet, -------------------
# in various contexts


class NotificationDocumentsView(DetailView):
    template_name = "gsl_notification/tab_simulation_projet/tab_notifications.html"
    pk_url_kwarg = "programmation_projet_id"
    context_object_name = "programmation_projet"

    def get_queryset(self):
        return ProgrammationProjet.objects.visible_to_user(self.request.user)

    def get_context_data(self, **kwargs):
        title = self.object.projet.dossier_ds.projet_intitule
        return super().get_context_data(
            **{
                "dotation_projet": self.object.dotation_projet,
                "dossier": self.object.dotation_projet.projet.dossier_ds,
                "projet": self.object.projet,
                "title": title,
                "breadcrumb_dict": {
                    "links": [
                        {
                            "url": reverse(
                                "gsl_programmation:programmation-projet-list"
                            ),
                            "title": "Programmation en cours",
                        },
                    ],
                    "current": title,
                },
                "is_instructor": self.request.user.ds_id
                in self.object.dossier.ds_instructeurs.values_list("ds_id", flat=True),
            }
        )


class NotificationMessageView(UpdateView):
    template_name = (
        "gsl_notification/tab_simulation_projet/tab_notifications_message.html"
    )

    pk_url_kwarg = "programmation_projet_id"
    context_object_name = "programmation_projet"
    form_class = NotificationMessageForm

    def get_queryset(self):
        return ProgrammationProjet.objects.visible_to_user(self.request.user)

    def get_context_data(self, **kwargs):
        title = self.object.projet.dossier_ds.projet_intitule
        return super().get_context_data(
            **{
                "dotation_projet": self.object.dotation_projet,
                "dossier": self.object.dotation_projet.projet.dossier_ds,
                "projet": self.object.projet,
                "title": title,
                "breadcrumb_dict": {
                    "links": [
                        {
                            "url": reverse(
                                "gsl_programmation:programmation-projet-list"
                            ),
                            "title": "Programmation en cours",
                        },
                        {
                            "url": reverse(
                                "gsl_programmation:programmation-projet-detail",
                                args=[self.object.id],
                            ),
                            "title": title,
                        },
                    ],
                    "current": title,
                },
            }
        )

    def form_valid(self, form):
        try:
            form.save(instructeur_id=self.request.user.ds_id)
        except DsServiceException as e:
            messages.error(
                self.request,
                f"Une erreur est survenue lors de l'envoi de la notification. {str(e)}",
            )
            return self.form_invalid(form)

        messages.success(
            self.request,
            "Le projet accepté a bien été notifié. Un message de notification a bien été envoyé au demandeur dans l’espace Démarches Simplifiées.",
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse(
            "gsl_programmation:programmation-projet-detail",
            args=[self.object.projet.id],
        )


@method_decorator(htmx_only, name="dispatch")
class CheckDsDossierUpToDateView(OpenHtmxModalMixin, DetailView):
    """
    This view is used to check if the dossier is up to date. It should be used in a modal.
    """

    template_name = "gsl_notification/modal/ds_dossier_not_up_to_date.html"
    pk_url_kwarg = "projet_id"
    context_object_name = "projet"
    modal_id = "dossier-not-up-to-date-modal"

    def get_queryset(self):
        return Projet.objects.for_user(self.request.user)

    def render_to_response(self, context, *args, **kwargs):
        dossier = self.object.dossier_ds
        client = DsClient()
        dossier_data = client.get_one_dossier(dossier.ds_number)
        date_modif_ds = dossier_data.get("dateDerniereModification", None)
        if date_modif_ds:
            date_modif_ds = timezone.datetime.fromisoformat(date_modif_ds)
            if date_modif_ds <= dossier.ds_date_derniere_modification:
                return HttpResponseClientRedirect(
                    reverse("gsl_notification:documents", args=[self.object.id])
                )

        return super().render_to_response(context, *args, **kwargs)


# Edition form for arrêté --------------------------------------------------------------


@require_http_methods(["GET"])
def choose_type_for_document_generation(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet.objects.visible_to_user(request.user),
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    context = {
        "programmation_projet": programmation_projet,
        "dossier": programmation_projet.dossier,
        "cancel_link": reverse(
            "gsl_notification:documents", args=[programmation_projet_id]
        ),
        "next_step_link": reverse(
            "gsl_notification:select-modele", args=[programmation_projet.id, "type"]
        ),
    }
    return render(
        request,
        "gsl_notification/generated_document/choose_generated_document_type.html",
        context=context,
    )


@require_http_methods(["GET"])
def select_modele(request, programmation_projet_id, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet.objects.visible_to_user(request.user),
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    _, page_title, page_step_title, _ = (
        _get_pp_attribute_page_title_and_page_step_title(
            document_type, programmation_projet, step=1
        )
    )

    dotation = programmation_projet.dotation_projet.dotation
    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    modele_class = get_modele_class(document_type)
    modeles = modele_class.objects.filter(dotation=dotation, perimetre__in=perimetres)

    context = {
        "programmation_projet": programmation_projet,
        "dotation": programmation_projet.dotation,
        "document_type": document_type,
        "page_title": page_title,
        "page_step_title": page_step_title,
        "cancel_link": reverse(
            "gsl_notification:documents", args=[programmation_projet_id]
        ),
        "modeles_list": [
            {
                "name": obj.name,
                "description": obj.description,
                "actions": [
                    {
                        "label": "Sélectionner",
                        "href": reverse(
                            "notification:modifier-document",
                            kwargs={
                                "programmation_projet_id": programmation_projet.id,
                                "document_type": document_type,
                            },
                            query={"modele_id": obj.id},
                        ),
                    },
                ],
            }
            for obj in modeles
        ],
    }
    return render(
        request,
        "gsl_notification/generated_document/select_modele.html",
        context=context,
    )


@csp_update({"style-src": [SELF, UNSAFE_INLINE]})
@require_http_methods(["GET", "POST"])
def change_document_view(request, programmation_projet_id, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet.objects.visible_to_user(request.user),
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    modele = None
    pp_attribute, page_title, page_step_title, is_creating = (
        _get_pp_attribute_page_title_and_page_step_title(
            document_type, programmation_projet, step=1
        )
    )
    document_class = get_document_class(document_type)
    modele_class = get_modele_class(document_type)
    form_class = get_form_class(document_type)

    if hasattr(programmation_projet, pp_attribute):
        document = getattr(programmation_projet, pp_attribute)
        modele = document.modele
    else:
        document = document_class()

    if request.GET.get("modele_id"):
        dotation = programmation_projet.dotation_projet.dotation
        perimetres = get_modele_perimetres(dotation, request.user.perimetre)
        modele = get_object_or_404(
            modele_class,
            id=request.GET.get("modele_id"),
            dotation=dotation,
            perimetre__in=perimetres,
        )
        document.content = replace_mentions_in_html(
            modele.content, programmation_projet
        )

    if modele is None:
        raise Http404("Il n'y a pas de modèle sélectionné.")

    if request.method == "POST":
        form = form_class(request.POST, instance=document)
        if form.is_valid():
            form.save()

            _add_success_message(request, is_creating, document_type, document.name)
            return _redirect_to_documents_view(request, programmation_projet.id)
        else:
            messages.error(request, "Erreur dans le formulaire")
            document = form.instance
    else:
        form = form_class(instance=document)

    context = {
        "arrete_form": form,
        "arrete_initial_content": mark_safe(document.content),
        "page_title": page_title,
        "page_step_title": page_step_title,
        "modele": modele,
        "document_type": document_type,
    }
    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return render(
        request,
        "gsl_notification/generated_document/change_document.html",
        context=context,
    )


def _get_pp_attribute_page_title_and_page_step_title(
    document_type, programmation_projet: ProgrammationProjet, step=1
):
    pp_attribute = "arrete" if document_type == ARRETE else "lettre_notification"
    is_creating = not hasattr(programmation_projet, pp_attribute)
    page_title = (
        f"{'Création' if is_creating else 'Modification'} de l'arrêté attributif"
    )
    if document_type == LETTRE:
        page_title = f"{'Création' if is_creating else 'Modification'} de la lettre de notification"

    if step == 1:
        page_step_title = "1 - Choix du modèle de "
    else:
        page_step_title = "2 - Publipostage de "

    if document_type == ARRETE:
        page_step_title += "l'arrêté"
    else:
        page_step_title += "la lettre de notification"

    return pp_attribute, page_title, page_step_title, is_creating


def _add_success_message(
    request, is_creating: bool, document_type: POSSIBLES_DOCUMENTS, document_name: str
):
    verbe = "créé" if is_creating else "modifié"
    type_and_article = (
        "L'arrêté" if document_type == ARRETE else "La lettre de notification"
    )
    accord = "e" if document_type == LETTRE else ""
    messages.info(
        request,
        f"{type_and_article} “{document_name}” a bien été {verbe}{accord}.",
    )


# Suppression d'arrêté -----------------------------------------------------------------


@document_visible_by_user
@require_http_methods(["POST"])
def delete_document_view(request, document_type, document_id):
    document_class = get_document_class(document_type)
    document = get_object_or_404(document_class, id=document_id)
    programmation_projet_id = document.programmation_projet.id

    document.delete()

    messages.success(request, "Le document a bien été supprimé.")

    return _redirect_to_documents_view(request, programmation_projet_id)


# View and Download views -----------------------------------------------------------------------


class PrintDocumentView(WeasyTemplateResponseMixin, DetailView):
    model = GeneratedDocument
    template_name = "gsl_notification/pdf/document.html"
    pk_url_kwarg = "document_id"

    # show pdf in-line (default: True, show download dialog)
    pdf_attachment = False

    def get_object(self, queryset=None):
        self.document_type = self.kwargs["document_type"]
        document_id = self.kwargs["document_id"]
        document_class = get_document_class(self.document_type)
        doc = get_object_or_404(document_class, id=document_id)
        return doc

    def get_pdf_filename(self):
        return self.get_object().name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_object()
        context.update(
            {
                "doc_title": get_doc_title(self.document_type),
                "logo": document.modele.logo.url,
                "alt_logo": document.modele.logo_alt_text,
                "top_right_text": document.modele.top_right_text.strip(),
                "content": mark_safe(document.content),
            }
        )
        return context


class DownloadDocumentView(PrintDocumentView):
    pdf_attachment = True


# utils --------------------------------------------------------------------------------


def _redirect_to_documents_view(request, programmation_projet_id):
    return redirect(
        reverse(
            "gsl_notification:documents",
            kwargs={"programmation_projet_id": programmation_projet_id},
        )
    )


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
