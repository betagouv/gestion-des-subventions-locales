from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import DeleteView, DetailView, UpdateView
from django_htmx.http import HttpResponseClientRedirect
from django_weasyprint import WeasyTemplateResponseMixin

from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_core.view_mixins import OpenHtmxModalMixin
from gsl_demarches_simplifiees.ds_client import DsClient
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_notification.forms import (
    ChooseDocumentTypeForGenerationForm,
    NotificationMessageForm,
)
from gsl_notification.models import (
    GeneratedDocument,
)
from gsl_notification.utils import (
    get_doc_title,
    get_form_class,
    get_generated_document_class,
    get_modele_class,
    get_modele_perimetres,
    get_uploaded_document_class,
    replace_mentions_in_html,
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
    pk_url_kwarg = "projet_id"
    context_object_name = "projet"

    def get_queryset(self):
        return Projet.objects.for_user(self.request.user)

    def get_context_data(self, **kwargs):
        title = self.object.dossier_ds.projet_intitule
        return super().get_context_data(
            **{
                "dossier": self.object.dossier_ds,
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
                in self.object.dossier_ds.ds_instructeurs.values_list(
                    "ds_id", flat=True
                ),
            }
        )


class NotificationMessageView(UpdateView):
    template_name = (
        "gsl_notification/tab_simulation_projet/tab_notifications_message.html"
    )

    pk_url_kwarg = "projet_id"
    context_object_name = "projet"
    form_class = NotificationMessageForm

    def get_queryset(self):
        return Projet.objects.for_user(self.request.user).can_send_notification()

    def get_context_data(self, **kwargs):
        title = self.object.dossier_ds.projet_intitule
        return super().get_context_data(
            **{
                "dossier": self.object.dossier_ds,
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
            form.save(user=self.request.user)
        except DsServiceException as e:
            messages.error(
                self.request,
                f"Une erreur est survenue lors de l'envoi de la notification. {str(e)}",
            )
            return self.form_invalid(form)

        messages.success(
            self.request,
            "Le dossier a bien été accepté sur Démarche Numérique.",
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse(
            "gsl_programmation:programmation-projet-detail",
            args=[self.object.id],
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


class ChooseDocumentTypeForGenerationView(UpdateView):
    template_name = (
        "gsl_notification/generated_document/choose_generated_document_type.html"
    )
    context_object_name = "projet"
    pk_url_kwarg = "projet_id"
    form_class = ChooseDocumentTypeForGenerationForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_link"] = reverse(
            "gsl_programmation:programmation-projet-detail", args=[self.object.id]
        )
        return context

    def get_queryset(self):
        return Projet.objects.for_user(self.request.user)

    def form_valid(self, form):
        return redirect(
            reverse(
                "gsl_notification:select-modele",
                args=[
                    self.object.id,
                    form.cleaned_data["document"]["dotation"],
                    form.cleaned_data["document"]["type"],
                ],
            )
        )


@require_http_methods(["GET"])
def select_modele(request, projet_id, dotation, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet.objects.visible_to_user(request.user).filter(
            status=ProgrammationProjet.STATUS_ACCEPTED
        ),
        dotation_projet__projet_id=projet_id,
        enveloppe__dotation=dotation,
    )
    _, page_title, page_step_title, _ = (
        _get_pp_attribute_page_title_and_page_step_title(
            document_type, programmation_projet, step=1
        )
    )

    dotation = programmation_projet.dotation_projet.dotation
    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    try:
        modele_class = get_modele_class(document_type)
    except ValueError:
        raise Http404(user_message="Le type de document sélectionné n'existe pas.")
    modeles = modele_class.objects.filter(dotation=dotation, perimetre__in=perimetres)

    context = {
        "projet": programmation_projet.projet,
        "programmation_projet": programmation_projet,
        "dotation": programmation_projet.dotation,
        "document_type": document_type,
        "page_title": page_title,
        "page_step_title": page_step_title,
        "cancel_link": reverse("gsl_notification:documents", args=[projet_id]),
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
                                "projet_id": projet_id,
                                "dotation": dotation,
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
def change_document_view(request, projet_id, dotation, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet.objects.visible_to_user(request.user).filter(
            status=ProgrammationProjet.STATUS_ACCEPTED
        ),
        dotation_projet__projet_id=projet_id,
        enveloppe__dotation=dotation,
    )
    modele = None
    pp_attribute, page_title, page_step_title, is_creating = (
        _get_pp_attribute_page_title_and_page_step_title(
            document_type, programmation_projet, step=1
        )
    )
    try:
        document_class = get_generated_document_class(document_type)
        modele_class = get_modele_class(document_type)
        form_class = get_form_class(document_type)
    except ValueError:
        raise Http404(user_message="Le type de document sélectionné n'existe pas.")

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
        raise Http404(user_message="Il n'y a pas de modèle sélectionné.")

    if request.method == "POST":
        form = form_class(request.POST, instance=document)
        if form.is_valid():
            form.save()

            _add_success_message(request, is_creating, document_type, document.name)
            return redirect(
                reverse(
                    "gsl_notification:documents",
                    kwargs={"projet_id": projet_id},
                )
            )
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


@method_decorator(require_POST, name="dispatch")
class DeleteDocumentView(DeleteView):
    context_object_name = "document"
    pk_url_kwarg = "document_id"

    def get_queryset(self):
        try:
            document_class = get_generated_document_class(self.kwargs["document_type"])
        except ValueError:
            try:
                document_class = get_uploaded_document_class(
                    self.kwargs["document_type"]
                )
            except ValueError:
                raise Http404(
                    user_message="Le type de document sélectionné n'existe pas."
                )
        return document_class.objects.filter(
            programmation_projet__dotation_projet__projet__in=Projet.objects.for_user(
                self.request.user
            )
        )

    def form_valid(self, form):
        messages.success(self.request, "Le document a bien été supprimé.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "gsl_notification:documents",
            kwargs={"projet_id": self.object.programmation_projet.projet.id},
        )


# View and Download views -----------------------------------------------------------------------


class PrintDocumentView(WeasyTemplateResponseMixin, DetailView):
    model = GeneratedDocument
    template_name = "gsl_notification/pdf/document.html"
    pk_url_kwarg = "document_id"

    # show pdf in-line (default: True, show download dialog)
    pdf_attachment = False

    def get_queryset(self):
        self.document_type = self.kwargs["document_type"]
        try:
            document_class = get_generated_document_class(self.document_type)
        except ValueError:
            raise Http404(user_message="Le type de document sélectionné n'existe pas.")

        return document_class.objects.filter(
            programmation_projet__dotation_projet__projet__in=Projet.objects.for_user(
                self.request.user
            )
        )

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
