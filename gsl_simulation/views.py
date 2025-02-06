import logging

from django.core.paginator import Paginator
from django.db.models import Prefetch, Sum
from django.http import JsonResponse
from django.http.request import QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django_filters.views import FilterView

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_projet.models import Projet
from gsl_projet.services import ProjetService
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.views import ProjetFilters
from gsl_simulation.forms import SimulationForm
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.services.simulation_projet_service import (
    SimulationProjetService,
)
from gsl_simulation.services.simulation_service import SimulationService
from gsl_simulation.tasks import add_enveloppe_projets_to_simulation
from gsl_simulation.utils import get_filters_dict_from_params, replace_comma_by_dot


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

    def get_queryset(self):
        visible_by_user_enveloppes = EnveloppeService.get_enveloppes_visible_for_a_user(
            self.request.user
        )
        return Simulation.objects.filter(
            enveloppe__in=visible_by_user_enveloppes
        ).order_by("-created_at")


class SimulationProjetListViewFilters(ProjetFilters):
    filterset = (
        "porteur",
        "status",
        "cout_total",
        "montant_demande",
        "montant_retenu",
    )

    class Meta(ProjetFilters.Meta):
        fields = (
            "porteur",
            "cout_min",
            "cout_max",
            "montant_demande_min",
            "montant_demande_max",
            "montant_retenu_min",
            "montant_retenu_max",
            "status",
        )


class SimulationDetailView(FilterView, DetailView, FilterUtils):
    model = Simulation
    filterset_class = SimulationProjetListViewFilters
    template_name = "gsl_simulation/simulation_detail.html"

    def get(self, request, *args, **kwargs):
        # Ensure the object is retrieved
        self.simulation = self.get_object()
        self.object = self.simulation
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        qs = self.get_projet_queryset()
        context = super().get_context_data(**kwargs)
        paginator = Paginator(qs, 25)  # TODO try with paginate_by
        page = self.kwargs.get("page") or self.request.GET.get("page") or 1
        current_page = paginator.page(page)
        context["simulations_paginator"] = current_page
        context["simulations_list"] = current_page.object_list
        context["title"] = (
            f"{self.simulation.enveloppe.type} {self.simulation.enveloppe.annee} – {self.simulation.title}"
        )
        context["porteur_mappings"] = ProjetService.PORTEUR_MAPPINGS
        context["status_summary"] = self.simulation.get_projet_status_summary()
        context["total_cost"] = ProjetService.get_total_cost(qs)
        context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs)
        context["total_amount_granted"] = ProjetService.get_total_amount_granted(qs)
        context["available_states"] = SimulationProjet.STATUS_CHOICES
        context["filter_params"] = self.request.GET.urlencode()
        context["enveloppe"] = self.get_enveloppe_data(self.simulation)
        self.enrich_context_with_filter_utils(context)

        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("simulation:simulation-list"),
                    "title": "Mes simulations de programmation",
                }
            ],
            "current": self.simulation.title,
        }

        return context

    def get_projet_queryset(self):
        simulation = self.get_object()
        qs = self.get_filterset(self.filterset_class).qs
        qs = SimulationService.filter_projets_from_simulation(qs, simulation)
        qs = qs.prefetch_related(
            Prefetch(
                "simulationprojet_set",
                queryset=SimulationProjet.objects.filter(simulation=simulation),
                to_attr="simu",
            )
        )
        qs.distinct()
        return qs

    def get_enveloppe_data(self, simulation):
        enveloppe = simulation.enveloppe
        enveloppe_projets_included = Projet.objects.included_in_enveloppe(enveloppe)
        enveloppe_projets_processed = Projet.objects.processed_in_enveloppe(enveloppe)

        montant_asked = enveloppe_projets_included.aggregate(
            Sum("dossier_ds__demande_montant")
        )["dossier_ds__demande_montant__sum"]

        montant_accepte = enveloppe_projets_processed.filter(
            dossier_ds__ds_state=Dossier.STATE_ACCEPTE
        ).aggregate(Sum("dossier_ds__annotations_montant_accorde"))[
            "dossier_ds__annotations_montant_accorde__sum"
        ]

        return {
            "type": simulation.enveloppe.type,
            "montant": simulation.enveloppe.montant,
            "perimetre": simulation.enveloppe.perimetre,
            "montant_asked": montant_asked,
            "validated_projets_count": enveloppe_projets_processed.filter(
                dossier_ds__ds_state=Dossier.STATE_ACCEPTE
            ).count(),
            "montant_accepte": montant_accepte,
            "refused_projets_count": enveloppe_projets_processed.filter(
                dossier_ds__ds_state=Dossier.STATE_REFUSE
            ).count(),
            "demandeurs": enveloppe_projets_included.distinct("demandeur").count(),
            "projets_count": enveloppe_projets_included.count(),
        }


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
        "simulation:simulation-detail",
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


def simulation_form(request):
    if request.method == "POST":
        form = SimulationForm(request.POST, user=request.user)
        if form.is_valid():
            simulation = SimulationService.create_simulation(
                request.user, form.cleaned_data["title"], form.cleaned_data["dotation"]
            )
            add_enveloppe_projets_to_simulation(simulation.id)
            return redirect("simulation:simulation-list")
        else:
            return render(
                request, "gsl_simulation/simulation_form.html", {"form": form}
            )
    else:
        form = SimulationForm(user=request.user)
        context = {
            "breadcrumb_dict": {
                "links": [
                    {
                        "url": reverse("gsl_projet:list"),
                        "title": "Liste des projets",
                    },
                ],
                "current": "Création d'une simulation de programmation",
            }
        }
        context["form"] = form
        context["title"] = "Création d’une simulation de programmation"

        return render(request, "gsl_simulation/simulation_form.html", context)
