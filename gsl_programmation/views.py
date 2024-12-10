from django.core.paginator import Paginator
from django.urls import reverse
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from .models import Scenario, SimulationProjet


class ScenarioListView(ListView):
    model = Scenario
    paginate_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = (
            "Mes simulations"  # todo si filtre par année : rappeler l'année ici
        )
        return context


class ScenarioDetailView(DetailView):
    model = Scenario

    def get_context_data(self, **kwargs):
        scenario = self.get_object()
        context = super().get_context_data(**kwargs)
        paginator = Paginator(SimulationProjet.objects.filter(scenario=scenario), 25)
        page = self.kwargs.get("page") or self.request.GET.get("page") or 1
        current_page = paginator.page(page)
        context["simulations_paginator"] = current_page
        context["simulations_list"] = current_page.object_list
        context["title"] = (
            f"{scenario.enveloppe.type} {scenario.enveloppe.annee} – {scenario.title}"
        )

        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("programmation:scenario_list"),
                    "title": "Mes simulations de programmation",
                }
            ],
            "current": scenario.title,
        }

        return context
