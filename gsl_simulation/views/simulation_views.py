from datetime import date
from functools import cached_property

from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.forms import NumberInput
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django_filters import MultipleChoiceFilter, NumberFilter
from django_filters.views import FilterView

from gsl_core.models import Perimetre
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL, DOTATIONS
from gsl_projet.models import CategorieDetr, DotationProjet
from gsl_projet.services.projet_services import ProjetService
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
)
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.utils.projet_filters import ProjetOrderingFilter
from gsl_projet.utils.utils import order_couples_tuple_by_first_value
from gsl_projet.views import BaseProjetFilters
from gsl_simulation.forms import SimulationForm
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.resources import (
    DetrSimulationProjetResource,
    DsilSimulationProjetResource,
)


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


class SimulationProjetListViewFilters(BaseProjetFilters):
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
            self.filters["categorie_detr"].extra["choices"] = tuple(
                (c.id, c.libelle)
                for c in CategorieDetr.objects.current_for_departement(
                    perimetre.departement
                )
            )

    filterset = (
        "territoire",
        "porteur",
        "status",
        "cout_total",
        "montant_demande",
        "montant_previsionnel",
        "categorie_detr",
    )

    ORDERING_MAP = {
        **BaseProjetFilters.ORDERING_MAP,
        "dotationprojet__simulationprojet__montant": "montant_previsionnel",
    }

    ORDERING_LABELS = {
        **BaseProjetFilters.ORDERING_LABELS,
        "dotationprojet__simulationprojet__montant": "Montant prévisionnel",
    }

    order = ProjetOrderingFilter(
        fields=ORDERING_MAP,
        field_labels=ORDERING_LABELS,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    ordered_status = (
        SimulationProjet.STATUS_PROCESSING,
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_DISMISSED,
    )

    status = MultipleChoiceFilter(
        field_name="dotationprojet__simulationprojet__status",
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
            dotationprojet__simulationprojet__status__in=value,
        )

    montant_previsionnel_min = NumberFilter(
        field_name="dotationprojet__simulationprojet__montant",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
        method="filter_montant_previsionnel_min",
    )

    montant_previsionnel_max = NumberFilter(
        field_name="dotationprojet__simulationprojet__montant",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
        method="filter_montant_previsionnel_max",
    )

    def filter_montant_previsionnel_min(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            dotationprojet__simulationprojet__montant__gte=value,
        )

    def filter_montant_previsionnel_max(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            dotationprojet__simulationprojet__montant__lte=value,
        )

    def _simulation_slug_filter_kwarg(self):
        return {"dotationprojet__simulationprojet__simulation__slug": self.slug}


class SimulationDetailView(FilterView, DetailView, FilterUtils):
    model = Simulation
    filterset_class = SimulationProjetListViewFilters
    template_name = "gsl_simulation/simulation_detail.html"
    STATE_MAPPINGS = {key: value for key, value in SimulationProjet.STATUS_CHOICES}

    def get(self, request, *args, **kwargs):
        if "reset_filters" in request.GET:
            if request.path.startswith("/simulation/voir/"):
                return redirect(request.path)
            else:
                return redirect("/")

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

    def get_object(self, queryset=None):
        # surcharge pour éviter les requêtes multiples
        if hasattr(self, "object") and self.object:
            return self.object
        return super().get_object(queryset)

    def get_context_data(self, **kwargs):
        simulation = self.simulation
        qs = self.get_projet_queryset()
        context = super().get_context_data(**kwargs)
        paginator = Paginator(qs, 25)
        page = self.kwargs.get("page") or self.request.GET.get("page") or 1
        current_page = paginator.page(page)
        context.update(
            {
                "simulation": simulation,
                "simulation_paginator": current_page,
                "simulation_projets_list": current_page.object_list,
                "title": f"{simulation.enveloppe.dotation} {simulation.enveloppe.annee} – {simulation.title}",
                "status_summary": simulation.get_projet_status_summary(),
                "total_cost": ProjetService.get_total_cost(qs),
                "total_amount_asked": ProjetService.get_total_amount_asked(qs),
                "total_amount_granted": simulation.get_total_amount_granted(qs),
                "available_states": SimulationProjet.STATUS_CHOICES,
                "filter_params": self.request.GET.urlencode(),
                "enveloppe": simulation.enveloppe,
                "dotations": DOTATIONS,
                "export_types": FilteredProjetsExportView.EXPORT_TYPES,
                "breadcrumb_dict": {
                    "links": [
                        {
                            "url": reverse("simulation:simulation-list"),
                            "title": "Mes simulations de programmation",
                        }
                    ],
                    "current": simulation.title,
                },
            }
        )
        self.enrich_context_with_filter_utils(context, self.STATE_MAPPINGS)

        return context

    def get_projet_queryset(self):
        simulation = self.get_object()
        qs = self.get_filterset(self.filterset_class).qs
        qs = qs.filter(dotationprojet__simulationprojet__simulation=simulation)
        qs = qs.select_related("demandeur", "address", "address__commune")
        qs = qs.prefetch_related(
            "dotationprojet_set",
            "dotationprojet_set__programmation_projet",
            "dotationprojet_set__simulationprojet_set",
            # "dotationprojet_set__detr_categories", # TODO category : useless now. Remove it if we don't allow to set DETR category. The code is commented to enhance performance.
            "dossier_ds__demande_categorie_detr",
            "dossier_ds__demande_categorie_dsil",
            Prefetch(
                "dotationprojet_set",
                queryset=DotationProjet.objects.filter(
                    dotation=simulation.enveloppe.dotation
                ),
                to_attr="dotation_projet",
            ),
            Prefetch(
                "dotation_projet__simulationprojet_set",
                queryset=SimulationProjet.objects.filter(simulation=simulation),
                to_attr="simu",
            ),
            "dotation_projet__programmation_projet",
        )
        # TODO category : useless now. Remove it if we don't allow to set DETR category.
        # if simulation.dotation == DOTATION_DETR:
        #     qs = qs.prefetch_related(
        #         "dotation_projet__detr_categories",
        #     )

        qs.distinct()
        return qs

    def _get_perimetre(self) -> Perimetre:
        return self.perimetre

    def _get_territoire_choices(self):
        perimetre = self.perimetre
        return (perimetre, *perimetre.children())

    # TODO category : useless now. Remove it unless we use it to filter DETR projects.
    @cached_property
    def categorie_detr_choices(self):
        simulation = self.get_object()
        if simulation.dotation != DOTATION_DETR:
            return []

        return tuple(
            CategorieDetr.objects.current_for_departement(
                simulation.enveloppe.perimetre.departement
            ).all()
        )

    # This method is used to prevent caching of the page
    # This is useful for the row update with htmx
    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response


@method_decorator(require_POST, name="dispatch")
class SimulationDeleteView(DeleteView):
    success_url = reverse_lazy("simulation:simulation-list")

    def get_queryset(self):
        visible_by_user_enveloppes = EnveloppeService.get_enveloppes_visible_for_a_user(
            self.request.user
        )
        return Simulation.objects.filter(
            enveloppe__in=visible_by_user_enveloppes
        ).order_by("-created_at")


class SimulationCreateView(CreateView):
    model = Simulation
    form_class = SimulationForm
    template_name = "gsl_simulation/simulation_form.html"
    success_url = reverse_lazy("simulation:simulation-list")

    def get_form_kwargs(self):
        return {"user": self.request.user, **super().get_form_kwargs()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("gsl_simulation:simulation-list"),
                    "title": "Mes simulations de programmation",
                },
            ],
            "current": "Création d'une simulation de programmation",
        }
        context["title"] = "Création d'une simulation de programmation"
        return context


class FilteredProjetsExportView(SimulationDetailView):
    XLS = "xls"
    XLSX = "xlsx"
    CSV = "csv"
    ODS = "ods"
    EXPORT_TYPES = [XLS, XLSX, CSV, ODS]
    EXPORT_TYPE_TO_CONTENT_TYPE = {
        XLS: "application/vnd.ms-excel",
        XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        CSV: "text/csv",
        ODS: "application/vnd.oasis.opendocument.spreadsheet",
    }

    def get(self, request, *args, **kwargs):
        export_type = self.kwargs.get("type")
        if export_type not in self.EXPORT_TYPES:
            return HttpResponse("Invalid export type", status=400)

        self.object = self.get_object()
        self.simulation = Simulation.objects.get(slug=self.object.slug)
        queryset = self.get_projet_queryset()
        simu_projet_qs = SimulationProjet.objects.filter(
            simulation=self.simulation, dotation_projet__projet__in=queryset
        ).select_related(
            "dotation_projet",
            "dotation_projet__projet",
            "dotation_projet__projet__dossier_ds",
            "dotation_projet__projet__demandeur",
            "dotation_projet__projet__demandeur__address",
            "dotation_projet__projet__demandeur__address__commune",
            "dotation_projet__projet__demandeur__address__commune__arrondissement",
        )

        resource = (
            DsilSimulationProjetResource()
            if self.simulation.dotation == DOTATION_DSIL
            else DetrSimulationProjetResource()
        )
        dataset = resource.export(simu_projet_qs)

        export_data = dataset.export(export_type)
        content_type = self.EXPORT_TYPE_TO_CONTENT_TYPE[export_type]

        response = HttpResponse(export_data, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{date.today().strftime("%Y-%m-%d")} simulation {self.simulation.title}.{export_type}"'
        )
        return response
