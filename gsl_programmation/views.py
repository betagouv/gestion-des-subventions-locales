from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.urls import reverse
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

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
        context["breadcrumb_dict"] = {"current": "Liste des simulations"}

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
