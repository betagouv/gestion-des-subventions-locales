from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views.generic import ListView
from django_filters.views import FilterView

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.services import ProjetService
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.utils.projet_filters import ProjetFilters

from .models import Projet


@require_GET
def get_projet(request, projet_id):
    projet = get_object_or_404(Projet, id=projet_id)
    context = {
        "title": f"Projet {projet}",
        "projet": projet,
        "dossier": projet.dossier_ds,
        "breadcrumb_dict": {
            "links": [{"url": reverse("projet:list"), "title": "Liste des projets"}],
            "current": f"Projet {projet}",
        },
        "menu_dict": {
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
                            "label": "Coûts de financement",
                            "link": "#couts_financement",
                        },
                        {
                            "label": "Détails  du financement",
                            "link": "#detail_financement",
                        },
                        {
                            "label": "Dispositifs de financement sollicités",
                            "link": "#dispositifs_sollicites",
                        },
                        # {
                        #    "label": "Autres opérations en demande de subvention DETR/DSIL 2024",
                        #    "link": "(OR) the link (fragment) of the menu item",
                        # },
                    ),
                },
            ),
        },
    }
    return render(request, "gsl_projet/projet.html", context)


class ProjetListViewFilters(ProjetFilters):
    @property
    def qs(self):
        qs = super().qs
        qs = qs.for_user(self.request.user)
        qs = qs.for_current_year()
        qs = qs.select_related(
            "address",
            "address__commune",
        ).prefetch_related(
            "dossier_ds__demande_eligibilite_detr",
            "dossier_ds__demande_eligibilite_dsil",
        )
        return qs


class ProjetListView(FilterView, ListView, FilterUtils):
    model = Projet
    paginate_by = 25
    filterset_class = ProjetListViewFilters
    template_name = "gsl_projet/projet_list.html"
    STATE_MAPPINGS = {key: value for key, value in Dossier.DS_STATE_VALUES}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()  # TODO => is this linked to the filterset_class ???
        context["title"] = "Projets 2025"
        context["porteur_mappings"] = ProjetService.PORTEUR_MAPPINGS
        context["breadcrumb_dict"] = {"current": "Liste des projets"}
        context["total_cost"] = ProjetService.get_total_cost(qs)
        context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs)
        context["total_amount_granted"] = 0  # TODO
        self.enrich_context_with_filter_utils(context, self.STATE_MAPPINGS)

        return context
