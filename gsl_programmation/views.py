import logging

from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from django.http.request import QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from gsl_programmation.services import (
    ProjetService,
    SimulationProjetService,
    SimulationService,
    EnveloppeService,
)
from gsl_programmation.utils import get_filters_dict_from_params, replace_comma_by_dot
from gsl_projet.models import Projet

from .models import Simulation, SimulationProjet


class SimulationListView(ListView):
    model = Simulation
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = (
            "Mes simulations"  # todo si filtre par année : rappeler l'année ici
        )
        context["breadcrumb_dict"] = {"current": "Mes simulations de programmation"}

        return context


class SimulationDetailView(DetailView):
    model = Simulation

    def get_context_data(self, **kwargs):
        simulation = self.get_object()
        qs = self.get_projet_queryset()
        context = super().get_context_data(**kwargs)
        paginator = Paginator(qs, 25)
        page = self.kwargs.get("page") or self.request.GET.get("page") or 1
        current_page = paginator.page(page)
        context["simulations_paginator"] = current_page
        context["simulations_list"] = current_page.object_list
        context["title"] = (
            f"{simulation.enveloppe.type} {simulation.enveloppe.annee} – {simulation.title}"
        )
        context["porteur_mappings"] = ProjetService.PORTEUR_MAPPINGS
        context["status_summary"] = simulation.get_projet_status_summary()
        context["total_cost"] = ProjetService.get_total_cost(qs)
        context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs)
        context["total_amount_granted"] = ProjetService.get_total_amount_granted(qs)
        context["available_states"] = SimulationProjet.STATUS_CHOICES
        context["filter_params"] = self.request.GET.urlencode()
        context["enveloppe"] = {
            "type": simulation.enveloppe.type,
            "montant": simulation.enveloppe.montant,
            "perimetre": simulation.enveloppe.perimetre,
        }

        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("programmation:simulation_list"),
                    "title": "Mes simulations de programmation",
                }
            ],
            "current": simulation.title,
        }

        return context

    def get_projet_queryset(self):
        simulation = self.get_object()
        qs = SimulationService.get_projets_from_simulation(simulation)
        qs = qs.order_by("simulationprojet__created_at")
        qs = ProjetService.add_filters_to_projets_qs(qs, self.request.GET)
        qs = ProjetService.add_ordering_to_projets_qs(qs, self.request.GET.get("tri"))
        qs = qs.select_related("address").select_related("address__commune")
        qs = qs.prefetch_related(
            Prefetch(
                "simulationprojet_set",
                queryset=SimulationProjet.objects.filter(simulation=simulation),
                to_attr="simu",
            )
        )
        qs.distinct()
        return qs


def redirect_to_simulation_projet(request, simulation_projet):
    if request.htmx:
        projets_of_simulation = Projet.objects.filter(
            simulationprojet__simulation=simulation_projet.simulation
        )
        filter_params = QueryDict(request.body).get("filter_params")
        filters_dict = get_filters_dict_from_params(filter_params)
        filtered_projets_of_simulation = ProjetService.add_filters_to_projets_qs(
            projets_of_simulation,
            filters_dict,
        )
        total_amount_granted = ProjetService.get_total_amount_granted(
            filtered_projets_of_simulation
        )

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
        "programmation:simulation_detail",
        kwargs={"slug": simulation_projet.simulation.slug},
    )
    if request.POST.get("filter_params"):
        url += "?" + request.POST.get("filter_params")

    return redirect(url)


def exception_handler_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error("An error occurred: %s", str(e))
            return JsonResponse(
                {
                    "success": False,
                    "error": f"An internal error has occurred : {str(e)}",
                }
            )

    return wrapper


# TODO pour les fonctions ci-dessous : vérifier que l'utilisateur a les droits nécessaires
@exception_handler_decorator
@require_http_methods(["POST", "PATCH"])
def patch_taux_simulation_projet(request, pk):
    simulation_projet = SimulationProjet.objects.get(id=pk)
    data = QueryDict(request.body)

    new_taux = replace_comma_by_dot(data.get("taux"))
    SimulationProjetService.update_taux(simulation_projet, new_taux)
    return redirect_to_simulation_projet(request, simulation_projet)


@exception_handler_decorator
@require_http_methods(["POST", "PATCH"])
def patch_montant_simulation_projet(request, pk):
    simulation_projet = SimulationProjet.objects.get(id=pk)
    data = QueryDict(request.body)

    new_montant = replace_comma_by_dot(data.get("montant"))
    SimulationProjetService.update_montant(simulation_projet, new_montant)
    return redirect_to_simulation_projet(request, simulation_projet)


@exception_handler_decorator
@require_http_methods(["POST", "PATCH"])
def patch_status_simulation_projet(request, pk):
    simulation_projet = SimulationProjet.objects.get(id=pk)
    data = QueryDict(request.body)
    new_status = data.get("status")

    SimulationProjetService.update_status(simulation_projet, new_status)
    return redirect_to_simulation_projet(request, simulation_projet)
