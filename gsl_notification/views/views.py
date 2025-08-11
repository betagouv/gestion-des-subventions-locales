from csp.constants import SELF, UNSAFE_INLINE
from csp.decorators import csp_update
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_http_methods
from django.views.generic import DetailView
from django_weasyprint import WeasyTemplateResponseMixin

from gsl_notification.forms import (
    ArreteSigneForm,
)
from gsl_notification.models import Arrete, ArreteSigne, LettreNotification
from gsl_notification.utils import (
    get_document_class,
    get_form_class,
    get_modele_class,
    get_modele_perimetres,
    get_s3_object,
    replace_mentions_in_html,
    return_document_as_a_dict,
    update_file_name_to_put_it_in_a_programmation_projet_folder,
)
from gsl_notification.views.decorators import (
    arrete_signe_visible_by_user,
    arrete_visible_by_user,
    programmation_projet_visible_by_user,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import ARRETE, LETTRE

# Views for listing notification documents on a programmationProjet, -------------------
# in various contexts


def _generic_documents_view(request, programmation_projet_id, source_url, context):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    documents = []

    try:
        arrete = programmation_projet.arrete
        context["arrete_modal_title"] = (
            f"Suppression de l'arrêté {arrete.name} créé avec Turgot"
        )
        documents.append(
            {
                **return_document_as_a_dict(arrete),
                "tag": "Créé sur Turgot",
                "actions": [
                    {
                        "name": "update",
                        "label": "Modifier",
                        "href": reverse(
                            "notification:modifier-document",
                            args=[programmation_projet.id, ARRETE],  # TODO update this
                        ),
                    },
                    {
                        "name": "delete",
                        "label": "Supprimer",
                        "form_id": "delete-arrete",
                        "aria_controls": "delete-arrete-confirmation-modal",
                        "action": reverse(
                            "notification:delete-arrete", args=[arrete.id]
                        ),
                    },
                ],
            }
        )
    except Arrete.DoesNotExist:
        pass

    try:
        lettre = programmation_projet.lettre_notification
        # context["arrete_modal_title"] = (
        #     f"Suppression de l'arrêté {arrete.name} créé avec Turgot"
        # )
        documents.append(
            {
                **return_document_as_a_dict(lettre),
                "tag": "Créé sur Turgot",
                "actions": [
                    {
                        "name": "update",
                        "label": "Modifier",
                        "href": reverse(
                            "notification:modifier-document",
                            args=[programmation_projet.id, LETTRE],
                        ),
                    },
                    # {
                    #     "name": "delete",
                    #     "label": "Supprimer",
                    #     "form_id": "delete-arrete",
                    #     "aria_controls": "delete-arrete-confirmation-modal",
                    #     "action": reverse(
                    #         "notification:delete-arrete", args=[arrete.id]
                    #     ),
                    # },
                ],
            }
        )
    except LettreNotification.DoesNotExist:
        pass

    try:
        arrete_signe = programmation_projet.arrete_signe
        context["arrete_signe_modal_title"] = (
            f"Suppression de l'arrêté {arrete_signe.name} créé par {arrete_signe.created_by}"
        )
        documents.append(
            {
                **return_document_as_a_dict(arrete_signe),
                "tag": "Fichier importé",
                "actions": [
                    {
                        "name": "delete",
                        "label": "Supprimer",
                        "form_id": "delete-arrete-signe",
                        "aria_controls": "delete-arrete-signe-confirmation-modal",
                        "action": reverse(
                            "notification:delete-arrete-signe", args=[arrete_signe.id]
                        ),
                    },
                ],
            }
        )

    except ArreteSigne.DoesNotExist:
        pass

    context.update(
        {
            "programmation_projet_id": programmation_projet.id,
            "source_url": source_url,
            "dossier": programmation_projet.projet.dossier_ds,
            "documents": documents,
        }
    )

    return render(
        request,
        "gsl_notification/tab_simulation_projet/tab_notifications.html",
        context=context,
    )


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


# Edition form for arrêté --------------------------------------------------------------
@require_http_methods(["GET"])
@programmation_projet_visible_by_user
def choose_type_for_document_generation(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    context = {"programmation_projet": programmation_projet}
    return render(
        request, "gsl_notification/choose_generated_document_type.html", context=context
    )


@require_http_methods(["GET"])
@programmation_projet_visible_by_user
def select_modele(request, programmation_projet_id, document_type):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )
    _, page_title, page_step_title = get_pp_attribute_page_title_and_page_step_title(
        document_type, programmation_projet, step=1
    )

    dotation = programmation_projet.dotation_projet.dotation
    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    modele_class = get_modele_class(document_type)
    modeles = modele_class.objects.filter(dotation=dotation, perimetre__in=perimetres)

    context = {
        "programmation_projet": programmation_projet,
        "page_title": page_title,
        "page_step_title": page_step_title,
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
    return render(request, "gsl_notification/select_modele.html", context=context)


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
    pp_attribute, page_title, page_step_title = (
        get_pp_attribute_page_title_and_page_step_title(
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

            return _redirect_to_documents_view(request, programmation_projet.id)
        else:
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
    return render(request, "gsl_notification/change_document.html", context=context)


def get_pp_attribute_page_title_and_page_step_title(
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

    return pp_attribute, page_title, page_step_title


# Suppression d'arrêté -----------------------------------------------------------------


@arrete_visible_by_user
@require_http_methods(["POST"])
def delete_arrete_view(request, arrete_id):
    arrete = get_object_or_404(Arrete, id=arrete_id)
    programmation_projet_id = arrete.programmation_projet.id

    arrete.delete()

    return _redirect_to_documents_view(request, programmation_projet_id)


# Upload arrêté signé ------------------------------------------------------------------


@programmation_projet_visible_by_user
@require_http_methods(["GET", "POST"])
def create_arrete_signe_view(request, programmation_projet_id):
    programmation_projet = get_object_or_404(
        ProgrammationProjet,
        id=programmation_projet_id,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )

    if request.method == "POST":
        form = ArreteSigneForm(request.POST, request.FILES)
        if form.is_valid():
            update_file_name_to_put_it_in_a_programmation_projet_folder(
                form.instance.file, programmation_projet.id
            )
            form.save()

            return _redirect_to_documents_view(request, programmation_projet.id)
    else:
        form = ArreteSigneForm()

    context = {
        "arrete_signe_form": form,
    }
    _enrich_context_for_create_or_get_arrete_view(
        context, programmation_projet, request
    )

    return render(request, "gsl_notification/upload_arrete_signe.html", context=context)


# Suppression d'arrêté signé ----------------------------------------------------------


@arrete_signe_visible_by_user
@require_http_methods(["POST"])
def delete_arrete_signe_view(request, arrete_signe_id):
    arrete_signe = get_object_or_404(ArreteSigne, id=arrete_signe_id)
    programmation_projet_id = arrete_signe.programmation_projet.id

    arrete_signe.delete()

    return _redirect_to_documents_view(request, programmation_projet_id)


# View and Download views -----------------------------------------------------------------------


class PrintArreteView(WeasyTemplateResponseMixin, DetailView):
    model = Arrete
    template_name = "gsl_notification/pdf/arrete.html"
    pk_url_kwarg = "arrete_id"

    # show pdf in-line (default: True, show download dialog)
    pdf_attachment = False

    def get_pdf_filename(self):
        return self.get_object().name

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        arrete = self.get_object()
        context.update(
            {
                "logo": arrete.modele.logo,
                "alt_logo": arrete.modele.logo_alt_text,
                "top_right_text": arrete.modele.top_right_text.strip(),
                "content": mark_safe(arrete.content),
            }
        )
        return context


class DownloadArreteView(PrintArreteView):
    pdf_attachment = True


@arrete_signe_visible_by_user
@require_GET
def download_arrete_signe(request, arrete_signe_id, download=True):
    arrete = get_object_or_404(ArreteSigne, id=arrete_signe_id)
    s3_object = get_s3_object(arrete.file.name)

    response = StreamingHttpResponse(
        iter(s3_object["Body"].iter_chunks()),
        content_type=s3_object["ContentType"],
    )
    response["Content-Disposition"] = (
        f'{"attachment" if download else "inline"}; filename="{arrete.file.name.split("/")[-1]}"'
    )
    return response


@arrete_signe_visible_by_user
@require_GET
def view_arrete_signe(request, arrete_signe_id):
    return download_arrete_signe(request, arrete_signe_id, False)


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
