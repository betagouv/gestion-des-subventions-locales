import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from gsl_programmation.services import SimulationProjetService
from gsl_programmation.utils import replace_comma_by_dot
from gsl_projet.models import Projet
from gsl_projet.views import FilterProjetsMixin

from .models import Simulation, SimulationProjet


class SimulationListView(ListView):
    model = Simulation
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = (
            "Mes simulations"  # todo si filtre par année : rappeler l'année ici
        )
        return context


class SimulationDetailView(DetailView, FilterProjetsMixin):
    model = Simulation

    def get_context_data(self, **kwargs):
        simulation = self.get_object()
        context = super().get_context_data(**kwargs)
        paginator = Paginator(
            self.get_projet_queryset(),
            25,
        )
        page = self.kwargs.get("page") or self.request.GET.get("page") or 1
        current_page = paginator.page(page)
        context["simulations_paginator"] = current_page
        context["simulations_list"] = current_page.object_list
        context["title"] = (
            f"{simulation.enveloppe.type} {simulation.enveloppe.annee} – {simulation.title}"
        )
        context["porteur_mappings"] = self.PORTEUR_MAPPINGS
        context["status_summary"] = simulation.get_projet_status_summary()
        context["total_cost"] = simulation.get_total_cost()
        context["total_amount_asked"] = simulation.get_total_amount_asked()
        context["total_amount_granted"] = simulation.get_total_amount_granted()
        context["available_states"] = SimulationProjet.STATUS_CHOICES

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
        qs = Projet.objects.filter(simulationprojet__simulation=simulation)
        qs = self.add_filters_to_projets_qs(qs)
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
    if request.method == "POST":
        return redirect(
            reverse(
                "programmation:simulation_detail",
                kwargs={"slug": simulation_projet.simulation.slug},
            )
        )

    elif request.method == "PATCH":
        return JsonResponse({"success": True})

    else:
        return JsonResponse({"success": False, "error": "Invalid request method"})


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
@staff_member_required
@require_http_methods(["POST", "PATCH"])
def patch_taux_simulation_projet(request):
    simulation_projet_id = request.POST.get("simulation_projet_id")
    simulation_projet = SimulationProjet.objects.get(id=simulation_projet_id)

    new_taux = replace_comma_by_dot(request.POST.get("taux"))
    SimulationProjetService.update_taux(simulation_projet, new_taux)
    return redirect_to_simulation_projet(request, simulation_projet)


@exception_handler_decorator
@staff_member_required
@require_http_methods(["POST", "PATCH"])
def patch_montant_simulation_projet(request):
    simulation_projet_id = request.POST.get("simulation_projet_id")
    simulation_projet = SimulationProjet.objects.get(id=simulation_projet_id)

    new_montant = replace_comma_by_dot(request.POST.get("montant"))
    SimulationProjetService.update_montant(simulation_projet, new_montant)
    return redirect_to_simulation_projet(request, simulation_projet)


@exception_handler_decorator
@staff_member_required
@require_http_methods(["POST", "PATCH"])
def patch_status_simulation_projet(request):
    simulation_projet_id = request.POST.get("simulation_projet_id")
    simulation_projet = SimulationProjet.objects.get(id=simulation_projet_id)

    new_status = request.POST.get("status")
    SimulationProjetService.update_status(simulation_projet, new_status)
    return redirect_to_simulation_projet(request, simulation_projet)
