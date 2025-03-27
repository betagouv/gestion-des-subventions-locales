from django.core.paginator import Paginator
from django.db.models import Prefetch, Sum
from django.forms import NumberInput
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django_filters import MultipleChoiceFilter, NumberFilter
from django_filters.views import FilterView

from gsl_core.models import Perimetre
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_projet.models import Projet
from gsl_projet.services import ProjetService
from gsl_projet.utils.django_filters_custom_widget import CustomCheckboxSelectMultiple
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.utils.utils import order_couples_tuple_by_first_value
from gsl_projet.views import ProjetFilters
from gsl_simulation.forms import SimulationForm
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.services.simulation_service import SimulationService
from gsl_simulation.tasks import add_enveloppe_projets_to_simulation


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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slug = self.request.resolver_match.kwargs.get("slug")
        simulation = Simulation.objects.select_related(
            "enveloppe",
            "enveloppe__perimetre",
            "enveloppe__perimetre__region",
            "enveloppe__perimetre__departement",
            "enveloppe__perimetre__arrondissement",
        ).get(slug=self.slug)
        enveloppe = simulation.enveloppe
        perimetre = enveloppe.perimetre

        if perimetre:
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )

    filterset = (
        "territoire",
        "porteur",
        "status",
        "cout_total",
        "montant_demande",
        "montant_previsionnel",
    )

    ordered_status = (
        SimulationProjet.STATUS_PROCESSING,
        SimulationProjet.STATUS_PROVISOIRE,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_DISMISSED,
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
        return {"simulationprojet__simulation__slug": self.slug}


class SimulationDetailView(FilterView, DetailView, FilterUtils):
    model = Simulation
    filterset_class = SimulationProjetListViewFilters
    template_name = "gsl_simulation/simulation_detail.html"
    STATE_MAPPINGS = {key: value for key, value in SimulationProjet.STATUS_CHOICES}

    def get(self, request, *args, **kwargs):
        if "reset_filters" in request.GET:
            return redirect(request.path)

        self.object = self.get_object()
        self.simulation = Simulation.objects.select_related(
            "enveloppe",
            "enveloppe__perimetre",
            "enveloppe__perimetre__region",
            "enveloppe__perimetre__departement",
            "enveloppe__perimetre__arrondissement",
        ).get(slug=self.object.slug)
        self.perimetre = self.simulation.enveloppe.perimetre
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        simulation = self.simulation
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
        context["status_summary"] = simulation.get_projet_status_summary()
        context["total_cost"] = ProjetService.get_total_cost(qs)
        context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs)
        context["total_amount_granted"] = SimulationService.get_total_amount_granted(
            qs, simulation
        )
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
        montant_asked = enveloppe_projets_included.aggregate(
            Sum("dossier_ds__demande_montant")
        )["dossier_ds__demande_montant__sum"]

        enveloppe_projets_processed = ProgrammationProjet.objects.filter(
            enveloppe=enveloppe
        )
        montant_accepte = (
            enveloppe_projets_processed.filter(
                status=ProgrammationProjet.STATUS_ACCEPTED
            ).aggregate(Sum("montant"))["montant__sum"]
            or 0
        )

        return {
            "type": simulation.enveloppe.type,
            "annee": simulation.enveloppe.annee,
            "montant": simulation.enveloppe.montant,
            "perimetre": simulation.enveloppe.perimetre,
            "montant_asked": montant_asked,
            "validated_projets_count": enveloppe_projets_processed.filter(
                status=ProgrammationProjet.STATUS_ACCEPTED
            ).count(),
            "montant_accepte": montant_accepte,
            "refused_projets_count": enveloppe_projets_processed.filter(
                status=ProgrammationProjet.STATUS_REFUSED
            ).count(),
            "demandeurs": enveloppe_projets_included.distinct("demandeur").count(),
            "projets_count": enveloppe_projets_included.count(),
        }

    def _get_perimetre(self) -> Perimetre:
        return self.perimetre

    def _get_territoire_choices(self):
        perimetre = self.perimetre
        return (perimetre, *perimetre.children())

    # This method is used to prevent caching of the page
    # This is useful for the row update with htmx
    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response


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
