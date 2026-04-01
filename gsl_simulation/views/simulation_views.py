from datetime import date

from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, UpdateView
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.list import ListView
from django_filters.views import FilterView

from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_CREATION_SIMULATION,
    MATOMO_ACTION_EXPORT,
    MATOMO_CATEGORY_SIMULATION,
)
from gsl_core.models import Perimetre
from gsl_core.view_mixins import NoFeedbackHtmxFormViewMixin
from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_projet.constants import DOTATION_DSIL, DOTATIONS
from gsl_projet.models import DotationProjet, Projet
from gsl_simulation.filters import SimulationProjetFilters
from gsl_simulation.forms import (
    SimulationColumnsVisibilityForm,
    SimulationForm,
    SimulationRenameForm,
)
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.resources import (
    DetrSimulationProjetResource,
    DsilSimulationProjetResource,
)
from gsl_simulation.table_columns import SIMULATION_TABLE_COLUMNS


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


class SimulationDetailView(SingleObjectMixin, FilterView):
    queryset = Simulation.objects.select_related(
        "enveloppe",
        "enveloppe__perimetre",
        "enveloppe__perimetre__region",
        "enveloppe__perimetre__departement",
        "enveloppe__perimetre__arrondissement",
    )
    filterset_class = SimulationProjetFilters
    template_name = "gsl_simulation/simulation_detail.html"
    paginate_by = 25

    def get(self, request, *args, **kwargs):
        if "reset_filters" in request.GET:
            if request.path.startswith("/simulation/voir/"):
                return redirect(request.path)
            else:
                return redirect("/")

        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def get_filterset_kwargs(self, filterset_class):
        kwargs = super().get_filterset_kwargs(filterset_class)
        kwargs["queryset"] = self._get_projet_base_queryset()
        return kwargs

    def get_context_data(self, **kwargs):
        simulation = self.object
        context = super().get_context_data(**kwargs)
        aggregates = self.filterset.qs.totals()
        aggregates["total_amount_granted"] = simulation.get_total_amount_granted(
            self.filterset.qs
        )
        context.update(
            {
                "simulation": simulation,
                "title": f"{simulation.enveloppe.dotation} {simulation.enveloppe.annee} – {simulation.title}",
                "status_summary": simulation.get_projet_status_summary(),
                "enveloppe": simulation.enveloppe,
                "dotations": DOTATIONS,
                "current_order": self.request.GET.get("order", ""),
                "columns": SIMULATION_TABLE_COLUMNS,
                "aggregates": aggregates,
                "export_types": FilteredProjetsExportView.EXPORT_TYPES,
                "matomo_category_simulation": MATOMO_CATEGORY_SIMULATION,
                "matomo_action_export": MATOMO_ACTION_EXPORT,
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
        if self.object.enveloppe.perimetre:
            context["territoire_choices"] = (
                self.object.enveloppe.perimetre,
                *self.object.enveloppe.perimetre.children(),
            )

        return context

    def _get_projet_base_queryset(self):
        return (
            Projet.objects.filter(
                dotationprojet__simulationprojet__simulation=self.object
            )
            .select_related("demandeur", "address", "address__commune")
            .prefetch_related(
                "dotationprojet_set",
                "dotationprojet_set__programmation_projet",
                "dotationprojet_set__simulationprojet_set",
                "dossier_ds__demande_categorie_detr",
                "dossier_ds__demande_categorie_dsil",
                "dossier_ds__porteur_de_projet_arrondissement",
                "dossier_ds__ds_demarche",
                "dossier_ds__demande_cofinancements",
                "dossier_ds__projet_zonage",
                "dossier_ds__projet_contractualisation",
                Prefetch(
                    "dotationprojet_set",
                    queryset=DotationProjet.objects.filter(
                        dotation=self.object.enveloppe.dotation
                    ),
                    to_attr="dotation_projet",
                ),
                Prefetch(
                    "dotation_projet__simulationprojet_set",
                    queryset=SimulationProjet.objects.filter(simulation=self.object),
                    to_attr="simu",
                ),
                "dotation_projet__programmation_projet",
            )
            .defer("dossier_ds__ds_demarche__raw_ds_data")
            .distinct()
        )

    def _get_perimetre(self) -> Perimetre:
        return self.perimetre

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


class SimulationRenameView(UpdateView):
    form_class = SimulationRenameForm
    template_name = "gsl_simulation/simulation_rename.html"

    def get_queryset(self):
        visible_by_user_enveloppes = EnveloppeService.get_enveloppes_visible_for_a_user(
            self.request.user
        )
        return Simulation.objects.filter(enveloppe__in=visible_by_user_enveloppes)

    def _get_next_url(self):
        next_url = self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={self.request.get_host()}
        ):
            return next_url
        return None

    def get_success_url(self):
        return self._get_next_url() or self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        next_url = self._get_next_url()
        context["title"] = f"Renommer la simulation « {self.object.title} »"
        context["next_url"] = next_url
        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("gsl_simulation:simulation-list"),
                    "title": "Mes simulations de programmation",
                },
                {
                    "url": self.object.get_absolute_url(),
                    "title": self.object.title,
                },
            ],
            "current": "Renommer",
        }
        return context


class SimulationCreateView(CreateView):
    model = Simulation
    form_class = SimulationForm
    template_name = "gsl_simulation/simulation_form.html"

    success_url = reverse_lazy("simulation:simulation-list")

    def get_form_kwargs(self):
        return {"user": self.request.user, **super().get_form_kwargs()}

    def form_valid(self, form):
        response = super().form_valid(form)
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_SIMULATION,
            MATOMO_ACTION_CREATION_SIMULATION,
            self.object.enveloppe.dotation,
        )
        return response

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


class SimulationColumnsVisibilityView(NoFeedbackHtmxFormViewMixin, UpdateView):
    model = Simulation
    form_class = SimulationColumnsVisibilityForm

    def get_queryset(self):
        return Simulation.objects.filter(
            enveloppe__in=EnveloppeService.get_enveloppes_visible_for_a_user(
                self.request.user
            )
        )


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

    def get_projet_queryset(self):
        return self.get_filterset(self.filterset_class).qs

    def get(self, request, *args, **kwargs):
        export_type = self.kwargs.get("type")
        if export_type not in self.EXPORT_TYPES:
            return HttpResponse("Invalid export type", status=400)

        self.object = self.get_object()
        queryset = self.get_projet_queryset()
        simu_projet_qs = SimulationProjet.objects.filter(
            simulation=self.object, dotation_projet__projet__in=queryset
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
            DsilSimulationProjetResource(export_format=export_type)
            if self.object.dotation == DOTATION_DSIL
            else DetrSimulationProjetResource(export_format=export_type)
        )
        dataset = resource.export(simu_projet_qs)

        headers_to_remove = resource.get_headers_to_remove(
            self.object.columns_visibility
        )
        for header in headers_to_remove:
            del dataset[header]

        if export_type == self.CSV:
            export_data = dataset.export("csv", delimiter=";")
        else:
            export_data = dataset.export(export_type)
        content_type = self.EXPORT_TYPE_TO_CONTENT_TYPE[export_type]

        response = HttpResponse(export_data, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{date.today().strftime("%Y-%m-%d")} simulation {self.object.title}.{export_type}"'
        )
        return response
