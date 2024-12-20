from django.core.paginator import Paginator
from django.urls import reverse
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

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


class SimulationDetailView(DetailView):
    model = Simulation

    def get_context_data(self, **kwargs):
        simulation = self.get_object()
        context = super().get_context_data(**kwargs)
        paginator = Paginator(
            SimulationProjet.objects.filter(simulation=simulation), 25
        )
        page = self.kwargs.get("page") or self.request.GET.get("page") or 1
        current_page = paginator.page(page)
        context["simulations_paginator"] = current_page
        context["simulations_list"] = current_page.object_list
        context["title"] = (
            f"{simulation.enveloppe.type} {simulation.enveloppe.annee} – {simulation.title}"
        )

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
