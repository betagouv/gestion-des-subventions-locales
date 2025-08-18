from django.http import HttpResponseForbidden
from django.shortcuts import get_list_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from gsl_notification.utils import get_modele_class, get_modele_perimetres
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import ARRETE, LETTRE
from gsl_projet.models import Projet


@require_http_methods(["GET"])  # TODO test it
def choose_type_for_multiple_document_generation(request, dotation):
    ids = _get_pp_ids(request)
    if len(ids) == 1:  # TODO test it
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
    _check_if_projets_are_accessible_for_user(request, programmation_projets)

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
    ids = _get_pp_ids(request)
    pp_count = len(ids)

    if pp_count == 1:  # TODO test it
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
    _check_if_projets_are_accessible_for_user(request, programmation_projets)

    page_title, page_step_title = _get_attribute_page_title_and_page_step_title(
        document_type, pp_count, step=1
    )

    perimetres = get_modele_perimetres(dotation, request.user.perimetre)
    modele_class = get_modele_class(document_type)
    modeles = modele_class.objects.filter(dotation=dotation, perimetre__in=perimetres)
    go_back_link = _get_go_back_link(dotation)

    context = {
        # "programmation_projet": programmation_projet,
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
                        "href": "https://reporterre.net",
                        # "href": reverse(
                        #     "notification:modifier-document",
                        #     kwargs={
                        #         "programmation_projet_id": programmation_projet.id,
                        #         "document_type": document_type,
                        #     },
                        #     query={"modele_id": obj.id},
                        # ),
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


# Private


def _get_pp_ids(request):
    ids_str = request.GET.get("ids")
    if not ids_str:
        return HttpResponseForbidden("Aucun identifiant fourni.")

    ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
    return ids


def _check_if_projets_are_accessible_for_user(request, programmation_projets):
    projet_ids = [pp.projet.id for pp in programmation_projets]
    projet_ids_visible_by_user = Projet.objects.for_user(request.user).filter(
        id__in=projet_ids
    )

    if len(projet_ids) != len(projet_ids_visible_by_user):
        return HttpResponseForbidden(
            "Un ou plusieurs projets sont hors de votre périmètre."
        )


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
