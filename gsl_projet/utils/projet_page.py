from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def get_projet_go_back_context(request):
    back = request.GET.get("back", "")
    if back and url_has_allowed_host_and_scheme(back, allowed_hosts=request.get_host()):
        prog_list = reverse("gsl_programmation:programmation-projet-list")
        return {
            "go_back_link": back,
            "go_back_to_programmation": back.startswith(prog_list),
        }
    return {"go_back_link": reverse("projet:list"), "go_back_to_programmation": False}


PROJET_MENU = {
    "title": "Menu",
    "items": (
        {
            "label": "1 – Porteur de projet",
            "link": "#porteur_de_projet",
        },
        {
            "label": "2 – Présentation de l’opération",
            "items": (
                {
                    "label": "Projet",
                    "link": "#presentation_projet",
                },
                {
                    "label": "Dates",
                    "link": "#presentation_dates",
                },
                {
                    "label": "Détails du projet",
                    "link": "#presentation_details_proj",
                },
                {
                    "label": "Transition écologique",
                    "link": "#presentation_transition_eco",
                },
            ),
        },
        {
            "label": "3 – Plan de financement prévisionnel",
            "items": (
                {
                    "label": "Détails  du financement",
                    "link": "#detail_financement",
                },
                {
                    "label": "Dispositifs de financement sollicités",
                    "link": "#dispositifs_sollicites",
                },
                {
                    "label": "Coûts de financement",
                    "link": "#couts_financement",
                },
            ),
        },
    ),
}
