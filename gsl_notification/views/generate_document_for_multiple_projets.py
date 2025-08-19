from django.contrib import messages
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_list_or_404, get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from gsl_core.tests.factories import RequestFactory
from gsl_notification.utils import (
    get_document_class,
    get_modele_class,
    get_modele_perimetres,
    replace_mentions_in_html,
)
from gsl_notification.views.views import DownloadArreteView
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    ARRETE,
    DOTATIONS,
    LETTRE,
    POSSIBLE_DOTATIONS,
    POSSIBLES_DOCUMENTS,
)
from gsl_projet.models import Projet


@require_http_methods(["GET"])
def choose_type_for_multiple_document_generation(request, dotation):
    if dotation not in DOTATIONS:
        return HttpResponseBadRequest("Dotation inconnue")

    try:
        ids = _get_pp_ids(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    if len(ids) == 1:
        return redirect(
            reverse(
                "gsl_notification:choose-generated-document-type",
                kwargs={"programmation_projet_id": ids[0]},
            )
        )

    programmation_projets = get_list_or_404(
        ProgrammationProjet,
        id__in=ids,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )

    try:
        _check_if_projets_are_accessible_for_user(request, programmation_projets)
    except ValueError as e:
        return HttpResponseForbidden(str(e))

    title = f"{len(programmation_projets)} projets {dotation} sélectionnés"
    go_back_link = _get_go_back_link(dotation)
    context = {
        "programmation_projets": programmation_projets,
        "page_title": title,
        "go_back_link": go_back_link,
        "cancel_link": go_back_link,
        "next_step_link": reverse(
            "gsl_notification:select-modele-multiple",
            args=[dotation, "type"],
            query=request.GET,
        ),
    }
    return render(
        request,
        "gsl_notification/generated_document/multiple/choose_generated_document_type.html",
        context=context,
    )


@require_http_methods(["GET"])
def select_modele_multiple(request, dotation, document_type):
    if dotation not in DOTATIONS:
        return HttpResponseBadRequest("Dotation inconnue")
    if document_type not in [ARRETE, LETTRE]:
        return HttpResponseBadRequest("Type de document inconnu")

    try:
        ids = _get_pp_ids(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    pp_count = len(ids)
    if pp_count == 1:
        return redirect(
            reverse(
                "gsl_notification:select-modele",
                kwargs={
                    "programmation_projet_id": ids[0],
                    "document_type": document_type,
                },
            )
        )

    programmation_projets = get_list_or_404(
        ProgrammationProjet,
        id__in=ids,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    try:
        _check_if_projets_are_accessible_for_user(request, programmation_projets)
    except ValueError as e:
        return HttpResponseForbidden(e)

    page_title, page_step_title = _get_attribute_page_title_and_page_step_title(
        document_type, pp_count, step=1
    )

    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    modele_class = get_modele_class(document_type)
    modeles = modele_class.objects.filter(dotation=dotation, perimetre__in=perimetres)
    go_back_link = _get_go_back_link(dotation)

    context = {
        "page_super_title": f"{pp_count} projets {dotation} sélectionnés",
        "page_title": page_title,
        "page_step_title": page_step_title,
        "cancel_link": go_back_link,
        "modeles_list": [
            {
                "name": obj.name,
                "description": obj.description,
                "actions": [
                    {
                        "label": "Sélectionner",
                        "type": "submit",
                        "href": reverse(
                            "notification:save-documents",
                            kwargs={
                                "dotation": dotation,
                                "document_type": document_type,
                                "modele_id": obj.id,
                            },
                            query=request.GET,
                        ),
                    },
                ],
            }
            for obj in modeles
        ],
    }
    return render(
        request,
        "gsl_notification/generated_document/multiple/select_modele.html",
        context=context,
    )


@require_POST
def save_documents(
    request,
    dotation: POSSIBLE_DOTATIONS,
    document_type: POSSIBLES_DOCUMENTS,
    modele_id: int,
):
    if dotation not in DOTATIONS:
        return HttpResponseBadRequest("Dotation inconnue")
    if document_type not in [ARRETE, LETTRE]:
        return HttpResponseBadRequest("Type de document inconnu")

    try:
        ids = _get_pp_ids(request)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    pp_count = len(ids)
    if pp_count == 1:  # TODO test it
        return redirect(
            reverse(
                "gsl_notification:modifier-document",
                kwargs={
                    "programmation_projet_id": ids[0],
                    "document_type": document_type,
                },
            )
        )

    programmation_projets = get_list_or_404(
        ProgrammationProjet,
        id__in=ids,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        notified_at=None,
    )
    try:
        _check_if_projets_are_accessible_for_user(request, programmation_projets)
    except ValueError as e:
        return HttpResponseForbidden(e)

    document_class = get_document_class(document_type)

    modele_class = get_modele_class(document_type)
    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    modele = get_object_or_404(
        modele_class,
        id=modele_id,  # TODO test if modele not in user perimetre
        dotation=dotation,
        perimetre__in=perimetres,
    )

    documents_list = []

    for pp in programmation_projets:  # TODO test if pp already have this document
        try:
            document_class.objects.get(programmation_projet_id=pp.id).delete()
        except document_class.DoesNotExist:
            pass

        document = document_class()
        document.programmation_projet = pp
        document.modele = modele
        document.created_by = request.user
        document.content = replace_mentions_in_html(modele.content, pp)
        document.save()
        documents_list.append(document)

    doc_name = "arrêtés" if document_type == ARRETE else "lettres de notification"
    accord = "s" if document_type == ARRETE else "es"

    # download_url = reverse()
    messages.success(
        request,
        f"Les {len(documents_list)} {doc_name} ont bien été créé{accord}.",
        extra_tags="success",
    )
    return redirect(_get_go_back_link(dotation))


# def download_documents(request, dotation, document_type):
#     ids = _get_pp_ids(request)
#     pp_count = len(ids)

#     if pp_count == 1:  # TODO test it
#         return redirect(
#             reverse(
#                 "gsl_notification:modifier-document",
#                 kwargs={
#                     "programmation_projet_id": ids[0],
#                     "document_type": document_type,
#                 },
#             )
#         )

#     programmation_projets = get_list_or_404(
#         ProgrammationProjet,
#         id__in=ids,
#         status=ProgrammationProjet.STATUS_ACCEPTED,
#         notified_at=None,
#     )
#     _check_if_projets_are_accessible_for_user(request, programmation_projets)
#     pp_attr = get_programmation_projet_attribute(document_type)
#     documents = set(getattr(pp, pp_attr) for pp in programmation_projets)

#     zip_buffer = io.BytesIO()
#     with zipfile.ZipFile(zip_buffer, "w") as zip_file:
#         for document in documents:
#             pdf_content = generate_pdf_for_document(document, document_type)
#             filename = f"{document.programmation_projet.id}_{document.modele.name}.pdf"
#             zip_file.writestr(filename, pdf_content)
#     zip_buffer.seek(0)
#     response = HttpResponse(zip_buffer, content_type="application/zip")
#     response["Content-Disposition"] = 'attachment; filename="documents.zip"'


# Private


def _get_pp_ids(request):
    ids_str = request.GET.get("ids")
    if not ids_str:
        raise ValueError("Aucun id de programmation projet")

    ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
    return ids


def _check_if_projets_are_accessible_for_user(
    request, programmation_projets
):  # TODO test it, event with multiple same ids
    projet_ids = set(pp.projet.id for pp in programmation_projets)
    projet_ids_visible_by_user = Projet.objects.for_user(request.user).filter(
        id__in=projet_ids
    )

    if len(projet_ids) != len(projet_ids_visible_by_user):
        raise ValueError("Un ou plusieurs projets sont hors de votre périmètre.")


def _get_attribute_page_title_and_page_step_title(
    document_type,
    pp_count: int,
    step=1,
):
    page_title = f"Création de {pp_count} arrêtés attributifs"
    if document_type == LETTRE:
        page_title = f"Création de {pp_count} lettres de notification"

    if step == 1:
        page_step_title = "1 - Choix du modèle de "
    else:
        page_step_title = "2 - Publipostage de "

    if document_type == ARRETE:
        page_step_title += "l'arrêté"
    else:
        page_step_title += "la lettre de notification"

    return page_title, page_step_title


def _get_go_back_link(dotation: str):
    return reverse(
        "gsl_programmation:programmation-projet-list-dotation",
        kwargs={"dotation": dotation},
    )


def generate_pdf_for_document(document, document_type):
    # Crée une requête factice pour la vue
    factory = RequestFactory()
    request = factory.get("/")
    request.user = document.created_by  # ou l'utilisateur courant

    # Instancie la vue
    view = DownloadArreteView()
    view.request = request
    view.kwargs = {"document_type": document_type, "document_id": document.id}
    view.object = document

    # Génère le PDF
    response = view.render_to_response(view.get_context_data())
    pdf_content = response.rendered_content  # ou response.content selon le type

    return pdf_content
