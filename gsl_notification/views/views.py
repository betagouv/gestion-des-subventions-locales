from typing import Union

from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_http_methods
from django.views.generic import DetailView
from django_weasyprint import WeasyTemplateResponseMixin

from gsl_notification.models import (
    Annexe,
    Arrete,
    ArreteEtLettreSignes,
    GeneratedDocument,
    LettreNotification,
)
from gsl_notification.utils import (
    get_doc_title,
    get_document_class,
    get_form_class,
    get_modele_class,
    get_modele_perimetres,
    replace_mentions_in_html,
    return_document_as_a_dict,
)
from gsl_notification.views.decorators import (
    document_visible_by_user,
    programmation_projet_visible_by_user,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    ANNEXE,
    ARRETE,
    ARRETE_ET_LETTRE_SIGNES,
    LETTRE,
    POSSIBLES_DOCUMENTS,
    POSSIBLES_DOCUMENTS_TELEVERSABLES,
)

# Views for listing notification documents on a programmationProjet, -------------------
# in various contexts


@programmation_projet_visible_by_user
@require_GET
def documents_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    projet = programmation_projet.projet
    title = projet.dossier_ds.projet_intitule
    context = {
        "programmation_projet": programmation_projet,
        "dotation_projet": programmation_projet.dotation_projet,
        "projet": projet,
        "dossier": projet.dossier_ds,
        "title": title,
        "breadcrumb_dict": {
            "links": [
                {
                    "url": reverse("gsl_programmation:programmation-projet-list"),
                    "title": "Programmation en cours",
                },
            ],
            "current": title,
        },
    }

    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )
    return _generic_documents_view(
        request,
        programmation_projet_id,
        programmation_projet.get_absolute_url(),
        context,
    )


def _generic_documents_view(request, programmation_projet_id, source_url, context):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    documents = []

    try:
        arrete = programmation_projet.arrete
        documents.append(
            _get_doc_card_attributes(arrete, ARRETE, programmation_projet_id)
        )
    except Arrete.DoesNotExist:
        pass

    try:
        lettre = programmation_projet.lettre_notification
        documents.append(
            _get_doc_card_attributes(lettre, LETTRE, programmation_projet_id)
        )
    except LettreNotification.DoesNotExist:
        pass

    try:
        arrete_et_lettre_signes = programmation_projet.arrete_et_lettre_signes
        documents.append(
            _get_uploaded_doc_card_attributes(
                arrete_et_lettre_signes, ARRETE_ET_LETTRE_SIGNES
            )
        )
    except ArreteEtLettreSignes.DoesNotExist:
        pass

    for annexe in programmation_projet.annexes.prefetch_related("created_by").all():
        documents.append(_get_uploaded_doc_card_attributes(annexe, ANNEXE))

    context.update(
        {
            "programmation_projet_id": programmation_projet.id,
            "source_url": source_url,
            "dossier": programmation_projet.projet.dossier_ds,
            "documents": sorted(documents, key=lambda d: d["created_at"]),
        }
    )

    return render(
        request,
        "gsl_notification/tab_simulation_projet/tab_notifications.html",
        context=context,
    )


def _get_doc_card_attributes(
    doc: Union[Arrete, LettreNotification],
    doc_type: POSSIBLES_DOCUMENTS,
    programmation_projet_id: int,
):
    return {
        **return_document_as_a_dict(doc),
        "tag": "Créé sur Turgot",
        "actions": [
            {
                "name": "update",
                "label": "Modifier",
                "href": reverse(
                    "notification:modifier-document",
                    args=[programmation_projet_id, doc_type],
                ),
            },
            {
                "name": "delete",
                "label": "Supprimer",
                "form_id": "delete-document-form",
                "aria_controls": "delete-document-confirmation-modal",
                "action": reverse(
                    "notification:delete-document",
                    kwargs={"document_type": doc_type, "document_id": doc.id},
                ),
            },
        ],
    }


def _get_uploaded_doc_card_attributes(
    doc: Union[ArreteEtLettreSignes, Annexe],
    doc_type: POSSIBLES_DOCUMENTS_TELEVERSABLES,
):
    return {
        **return_document_as_a_dict(doc),
        "tag": "Fichier importé",
        "actions": [
            {
                "name": "delete",
                "label": "Supprimer",
                "form_id": "delete-document-form",
                "aria_controls": "delete-document-confirmation-modal",
                "action": reverse(
                    "notification:delete-uploaded-document", args=[doc_type, doc.id]
                ),
            },
        ],
    }


# Edition form for arrêté --------------------------------------------------------------


@require_http_methods(["GET"])
@programmation_projet_visible_by_user
def choose_type_for_document_generation(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
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
@programmation_projet_visible_by_user
def select_modele(request, programmation_projet_id, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
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
@programmation_projet_visible_by_user
def change_document_view(request, programmation_projet_id, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
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
                "logo": document.modele.logo,
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
