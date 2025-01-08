from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

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
        context["breadcrumb_dict"] = {"current": "Mes simulations de programmation"}

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
        context["total_cost"] = simulation.get_total_cost()

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


@staff_member_required
@require_http_methods(["POST", "PATCH"])
def patch_simulation_projet(request):
    simulation_projet_id = request.POST.get("simulation_projet_id")
    new_taux = replace_comma_by_dot(request.POST.get("taux"))
    new_montant = replace_comma_by_dot(request.POST.get("montant"))
    if new_taux is None and new_montant is None:
        return JsonResponse({"success": False, "error": "Missing required parameters"})

    try:
        simulation_projet = SimulationProjet.objects.get(id=simulation_projet_id)
        if new_taux:
            new_montant = (
                simulation_projet.projet.assiette_or_cout_total
                * Decimal(new_taux)
                / 100
            )
        else:
            new_taux = (
                simulation_projet.montant
                / Decimal(simulation_projet.projet.assiette_or_cout_total)
            ) * 100

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()

        if request.method == "POST":
            return redirect(
                reverse(
                    "programmation:simulation_detail",
                    kwargs={"slug": simulation_projet.simulation.slug},
                )
            )

        elif request.method == "PATCH":
            return JsonResponse({"success": True, "montant": new_montant})

    except SimulationProjet.DoesNotExist:
        return JsonResponse({"success": False, "error": "SimulationProjet not found"})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request method"})
