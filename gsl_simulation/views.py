import logging

from django.core.paginator import Paginator
from django.db.models import Prefetch, Sum
from django.forms import NumberInput
from django.http import HttpRequest, JsonResponse
from django.http.request import QueryDict
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.views.decorators.http import require_http_methods
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django_filters import MultipleChoiceFilter, NumberFilter
from django_filters.views import FilterView

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_projet.models import Projet
from gsl_projet.services import ProjetService
from gsl_projet.utils.django_filters_custom_widget import CustomCheckboxSelectMultiple
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.utils.utils import order_couples_tuple_by_first_value
from gsl_projet.views import ProjetFilters
from gsl_simulation.forms import SimulationForm
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.services.simulation_projet_service import (
    SimulationProjetService,
)
from gsl_simulation.services.simulation_service import SimulationService
from gsl_simulation.tasks import add_enveloppe_projets_to_simulation
from gsl_simulation.utils import replace_comma_by_dot


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
        qs = Simulation.objects.filter(
            enveloppe__in=visible_by_user_enveloppes
        ).order_by("-created_at")
        qs = qs.select_related(
            "enveloppe",
            "enveloppe__perimetre",
            "enveloppe__perimetre__region",
            "enveloppe__perimetre__departement",
        )

        return qs


class SimulationProjetListViewFilters(ProjetFilters):
    filterset = (
        "porteur",
        "status",
        "cout_total",
        "montant_demande",
        "montant_previsionnel",
    )

    ordered_status = (
        SimulationProjet.STATUS_DRAFT,
        SimulationProjet.STATUS_PROVISOIRE,
        SimulationProjet.STATUS_CANCELLED,
        SimulationProjet.STATUS_VALID,
    )

    status = MultipleChoiceFilter(
        field_name="simulationprojet__status",
        choices=order_couples_tuple_by_first_value(
            SimulationProjet.STATUS_CHOICES, ordered_status
        ),
        widget=CustomCheckboxSelectMultiple(),
        method="filter_status",
    )

    def filter_status(self, queryset, name, value):
        return queryset.filter(
            # Cette ligne est utile pour qu'on ait un "ET", cad, on filtre les projets de la simulation en cours ET sur les statuts sélectionnés.
            # Sans ça, on aurait dans l'ordre :
            # - les projets dont IL EXISTE UN SIMULATION_PROJET (pas forcément celui de la simulation en question) qui a un des statuts sélectionnés
            # - les simulation_projets de la simulation associés aux projets filtrés
            **self._simulation_slug_filter_kwarg(),
            simulationprojet__status__in=value,
        )

    montant_previsionnel_min = NumberFilter(
        field_name="simulationprojet__montant",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
        method="filter_montant_previsionnel_min",
    )

    montant_previsionnel_max = NumberFilter(
        field_name="simulationprojet__montant",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
        method="filter_montant_previsionnel_max",
    )

    def filter_montant_previsionnel_min(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            simulationprojet__montant__gte=value,
        )

    def filter_montant_previsionnel_max(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            simulationprojet__montant__lte=value,
        )

    def _simulation_slug_filter_kwarg(self):
        return {
            "simulationprojet__simulation__slug": self.request.resolver_match.kwargs.get(
                "slug"
            )
        }


class SimulationDetailView(FilterView, DetailView, FilterUtils):
    model = Simulation
    filterset_class = SimulationProjetListViewFilters
    template_name = "gsl_simulation/simulation_detail.html"
    STATE_MAPPINGS = {key: value for key, value in SimulationProjet.STATUS_CHOICES}

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

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
        context["enveloppe"] = self._get_enveloppe_data(simulation)
        self.enrich_context_with_filter_utils(context, self.STATE_MAPPINGS)

        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("simulation:simulation-list"),
                    "title": "Mes simulations de programmation",
                }
            ],
            "current": simulation.title,
        }

        return context

    def get_projet_queryset(self):
        simulation = self.get_object()
        qs = self.get_filterset(self.filterset_class).qs
        qs = qs.filter(simulationprojet__simulation=simulation)
        qs = qs.select_related("address", "address__commune")
        qs = qs.prefetch_related(
            Prefetch(
                "simulationprojet_set",
                queryset=SimulationProjet.objects.filter(simulation=simulation),
                to_attr="simu",
            )
        )
        qs.distinct()
        return qs

    def _get_enveloppe_data(self, simulation):
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
        context["title"] = "Création d'une simulation de programmation"

        return render(request, "gsl_simulation/simulation_form.html", context)
