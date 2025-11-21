import io
import logging
import zipfile

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_list_or_404, get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET, require_POST
from django_weasyprint.utils import django_url_fetcher
from weasyprint import HTML

from gsl import settings
from gsl_notification.models import Arrete, LettreNotification
from gsl_notification.utils import (
    get_doc_title,
    get_document_class,
    get_logo_base64,
    get_modele_class,
    get_modele_perimetres,
    get_programmation_projet_attribute,
    replace_mentions_in_html,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import (
    ARRETE,
    DOTATIONS,
    LETTRE,
    POSSIBLE_DOTATIONS,
    POSSIBLES_DOCUMENTS,
)
from gsl_projet.models import Projet

logger = logging.getLogger(__name__)


DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR = "Un ou plusieurs des projets n'est pas disponible pour une des raisons (identifiant inconnu, identifiant en double, projet déjà notifié ou refusé, projet associé à une autre dotation)."


@require_GET
def choose_type_for_multiple_document_generation(request, dotation):
    if dotation not in DOTATIONS:
        return HttpResponseBadRequest("Dotation inconnue")

    try:
        ids = _get_pp_ids(request)
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
            dotation_projet__projet__notified_at=None,
            dotation_projet__dotation=dotation,
        )
        if len(programmation_projets) < len(ids):
            return HttpResponseBadRequest(
                DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR
            )
        try:
            _check_if_projets_are_accessible_for_user(request, programmation_projets)
        except ValueError as e:
            return HttpResponseForbidden(str(e))

    except ValueError:
        filterset = ProgrammationProjetFilters(
            data=request.GET,
            request=request,
            select_related_objs=[],
            prefetch_related_objs=[],
        )
        programmation_projets = filterset.qs.to_notify()

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


@require_GET
def select_modele_multiple(request, dotation, document_type):
    if dotation not in DOTATIONS:
        return HttpResponseBadRequest("Dotation inconnue")
    if document_type not in [ARRETE, LETTRE]:
        return HttpResponseBadRequest("Type de document inconnu")

    try:
        ids = _get_pp_ids(request)
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
            dotation_projet__projet__notified_at=None,
            dotation_projet__dotation=dotation,
        )
        if len(programmation_projets) < len(ids):
            return HttpResponseBadRequest(
                DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR
            )
        try:
            _check_if_projets_are_accessible_for_user(request, programmation_projets)
        except ValueError as e:
            return HttpResponseForbidden(str(e))

    except ValueError:
        filterset = ProgrammationProjetFilters(
            data=request.GET,
            request=request,
            select_related_objs=[],
            prefetch_related_objs=[],
        )
        programmation_projets = filterset.qs.to_notify()
        pp_count = programmation_projets.count()

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
        "dotation": dotation,
        "document_type": document_type,
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
        pp_count = len(ids)
        if pp_count == 1:
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
            dotation_projet__projet__notified_at=None,
            dotation_projet__dotation=dotation,
        )
        if len(programmation_projets) < len(ids):
            return HttpResponseBadRequest(
                DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR
            )
        try:
            _check_if_projets_are_accessible_for_user(request, programmation_projets)
        except ValueError as e:
            return HttpResponseForbidden(str(e))

    except ValueError:
        filterset = ProgrammationProjetFilters(
            data=request.POST,
            request=request,
            select_related_objs=[
                "dotation_projet__projet__dossier_ds",
                "dotation_projet__projet__dossier_ds__ds_demandeur",
                "dotation_projet__projet__perimetre__departement",
            ],
            prefetch_related_objs=[],
        )
        programmation_projets = filterset.qs.to_notify()

    document_class = get_document_class(document_type)

    modele_class = get_modele_class(document_type)
    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    modele = get_object_or_404(
        modele_class,
        id=modele_id,
        dotation=dotation,
        perimetre__in=perimetres,
    )

    documents_list = []

    for pp in programmation_projets:
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

    download_url = reverse(
        "gsl_notification:download-documents",
        kwargs={
            "dotation": dotation,
            "document_type": document_type,
        },
        query=request.GET,
    )
    messages.success(
        request,
        f"Les {len(documents_list)} {doc_name} ont bien été créé{accord}. <a href={download_url} title='Déclenche le téléchargement du fichier zip'>Télécharger le fichier zip</a>",
    )
    return redirect(_get_go_back_link(dotation))


@require_GET
def download_documents(request, dotation, document_type):
    if dotation not in DOTATIONS:
        return HttpResponseBadRequest("Dotation inconnue")
    if document_type not in [ARRETE, LETTRE]:
        return HttpResponseBadRequest("Type de document inconnu")

    pp_attr = get_programmation_projet_attribute(document_type)
    attr_select_related = [
        "dotation_projet",
        "dotation_projet__projet",
        "dotation_projet__projet__dossier_ds",
        pp_attr,
        f"{pp_attr}__modele",
    ]

    try:
        ids = _get_pp_ids(request)
        pp_count = len(ids)
        if pp_count == 1:
            return redirect(
                reverse(
                    "gsl_notification:choose-generated-document-type",
                    kwargs={"programmation_projet_id": ids[0]},
                )
            )
        programmation_projets = get_list_or_404(
            ProgrammationProjet.objects.select_related(*attr_select_related),
            id__in=ids,
            dotation_projet__dotation=dotation,
            status=ProgrammationProjet.STATUS_ACCEPTED,
            dotation_projet__projet__notified_at=None,
        )
        if len(programmation_projets) < len(ids):
            return HttpResponseBadRequest(
                DIFFRENCE_BETWEEN_IDS_COUNT_AND_PP_COUNT_MSG_ERROR
            )
        try:
            _check_if_projets_are_accessible_for_user(request, programmation_projets)
        except ValueError as e:
            return HttpResponseForbidden(str(e))
    except ValueError:
        filterset = ProgrammationProjetFilters(
            data=request.GET,
            request=request,
            select_related_objs=[],
            prefetch_related_objs=[],
        )
        programmation_projets = filterset.qs.to_notify().select_related(
            *attr_select_related
        )

    try:
        documents = set(getattr(pp, pp_attr) for pp in programmation_projets)
    except (
        ProgrammationProjet.lettre_notification.RelatedObjectDoesNotExist,
        ProgrammationProjet.arrete.RelatedObjectDoesNotExist,
    ):
        return HttpResponseBadRequest("Un des projets n'a pas le document demandé.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for i, document in enumerate(documents, start=1):
            pdf_content = _generate_pdf_for_document(document, document_type)
            filename = f"{document.name}"
            zip_file.writestr(filename, pdf_content)
            logger.info(f"#{i} {document} généré")
    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer, content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="documents.zip"'
    return response


# Utils


def _get_pp_ids(request):
    ids_str = request.GET.get("ids")
    if not ids_str:
        raise ValueError("Aucun id de programmation projet")

    ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
    return ids


def _check_if_projets_are_accessible_for_user(request, programmation_projets):
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


def _generate_pdf_for_document(document: Arrete | LettreNotification, document_type):
    context = {
        "doc_title": get_doc_title(document_type),
        "logo": get_logo_base64(document.modele.logo.url),
        "alt_logo": document.modele.logo_alt_text,
        "top_right_text": document.modele.top_right_text.strip(),
        "content": mark_safe(document.content),
    }

    html_string = render_to_string("gsl_notification/pdf/document.html", context)

    pdf_content = HTML(
        string=html_string,
        url_fetcher=django_url_fetcher,
        base_url=settings.STATIC_ROOT,
    ).write_pdf()

    return pdf_content
