from django.http import HttpRequest
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import resolve, reverse
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView

from gsl_projet.services import ProjetService
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.simulation_projet_service import (
    SimulationProjetService,
)
from gsl_simulation.utils import replace_comma_by_dot
from gsl_simulation.views.decorators import (
    exception_handler_decorator,
    projet_must_be_in_user_perimetre,
)
from gsl_simulation.views.simulation_views import SimulationDetailView


def _get_projets_queryset_with_filters(simulation, filter_params):
    url = reverse(
        "simulation:simulation-detail",
        kwargs={"slug": simulation.slug},
    )
    new_request = HttpRequest()
    new_request.GET = QueryDict(filter_params)
    new_request.resolver_match = resolve(url)

    view = SimulationDetailView()
    view.object = simulation
    view.request = new_request
    view.kwargs = {"slug": simulation.slug}

    projets = view.get_projet_queryset()
    return projets


def redirect_to_simulation_projet(request, simulation_projet):
    if request.htmx:
        filter_params = QueryDict(request.body).get("filter_params")
        filtered_projets = _get_projets_queryset_with_filters(
            simulation_projet.simulation,
            filter_params,
        )

        total_amount_granted = ProjetService.get_total_amount_granted(filtered_projets)

        return render(
            request,
            "htmx/projet_update.html",
            {
                "simu": simulation_projet,
                "projet": simulation_projet.projet,
                "available_states": SimulationProjet.STATUS_CHOICES,
                "status_summary": simulation_projet.simulation.get_projet_status_summary(),
                "total_amount_granted": total_amount_granted,
                "filter_params": filter_params,
            },
        )

    url = reverse(
        "simulation:simulation-detail",
        kwargs={"slug": simulation_projet.simulation.slug},
    )
    if request.POST.get("filter_params"):
        url += "?" + request.POST.get("filter_params")

    return redirect(url)


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_http_methods(["POST", "PATCH"])
def patch_taux_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    data = QueryDict(request.body)

    new_taux = replace_comma_by_dot(data.get("taux"))
    ProjetService.validate_taux(new_taux)
    SimulationProjetService.update_taux(simulation_projet, new_taux)
    return redirect_to_simulation_projet(request, simulation_projet)


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_http_methods(["POST", "PATCH"])
def patch_montant_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    data = QueryDict(request.body)

    new_montant = replace_comma_by_dot(data.get("montant"))
    SimulationProjetService.update_montant(simulation_projet, new_montant)
    return redirect_to_simulation_projet(request, simulation_projet)


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_http_methods(["POST", "PATCH"])
def patch_status_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    data = QueryDict(request.body)
    status = data.get("status")

    if status not in dict(SimulationProjet.STATUS_CHOICES).keys():
        raise ValueError("Invalid status")

    updated_simulation_projet = SimulationProjetService.update_status(
        simulation_projet, status
    )
    return redirect_to_simulation_projet(request, updated_simulation_projet)


class SimulationProjetDetailView(DetailView):
    model = SimulationProjet
    template_name = "gsl_simulation/simulation_projet_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Projet modifiable"
        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("simulation:simulation-list"),
                    "title": "Mes simulations de programmation",
                },
                {
                    "url": reverse(
                        "simulation:simulation-detail",
                        kwargs={"slug": self.object.simulation.slug},
                    ),
                    "title": self.object.simulation.title,
                },
            ],
            "current": self.object.projet,
        }
        context["projet"] = self.object.projet
        context["simu"] = self.object
        context["menu_dict"] = {
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
        }

        return context
