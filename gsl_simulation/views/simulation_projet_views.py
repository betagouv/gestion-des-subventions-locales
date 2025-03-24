from django import forms
from django.forms import ModelForm
from django.http import Http404, HttpRequest
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import DetailView
from dsfr.forms import DsfrBaseForm

from gsl.settings import ALLOWED_HOSTS
from gsl_projet.models import Projet
from gsl_projet.services import ProjetService
from gsl_projet.utils.projet_page import PROJET_MENU
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.simulation_projet_service import (
    SimulationProjetService,
)
from gsl_simulation.services.simulation_service import SimulationService
from gsl_simulation.utils import add_success_message, replace_comma_by_dot
from gsl_simulation.views.decorators import (
    exception_handler_decorator,
    projet_must_be_in_user_perimetre,
)
from gsl_simulation.views.simulation_views import SimulationDetailView


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


def redirect_to_simulation_projet(
    request, simulation_projet, message_type: str | None = None
):
    if request.htmx:
        filter_params = request.POST.get("filter_params")
        filtered_projets = _get_projets_queryset_with_filters(
            simulation_projet.simulation,
            filter_params,
        )

        total_amount_granted = SimulationService.get_total_amount_granted(
            filtered_projets, simulation_projet.simulation
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

    add_success_message(request, message_type, simulation_projet)

    referer = request.headers.get("Referer")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts=ALLOWED_HOSTS
    ):
        return redirect(referer)
    return redirect(
        "simulation:simulation-detail", slug=simulation_projet.simulation.slug
    )


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_taux_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    new_taux = replace_comma_by_dot(request.POST.get("taux"))
    ProjetService.validate_taux(new_taux)
    SimulationProjetService.update_taux(simulation_projet, new_taux)
    return redirect_to_simulation_projet(request, simulation_projet)


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_montant_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    new_montant = replace_comma_by_dot(request.POST.get("montant"))
    ProjetService.validate_montant(new_montant, simulation_projet.projet)
    SimulationProjetService.update_montant(simulation_projet, new_montant)
    return redirect_to_simulation_projet(request, simulation_projet)


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_status_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    status = request.POST.get("status")

    if status not in dict(SimulationProjet.STATUS_CHOICES).keys():
        raise ValueError("Invalid status")

    updated_simulation_projet = SimulationProjetService.update_status(
        simulation_projet, status
    )
    return redirect_to_simulation_projet(request, updated_simulation_projet, status)


class SimulationProjetDetailView(DetailView):
    model = SimulationProjet

    ALLOWED_TABS = {"annotations", "demandeur", "historique"}

    def get_template_names(self):
        if "tab" in self.kwargs:
            tab = self.kwargs["tab"]
            if tab not in self.ALLOWED_TABS:
                raise Http404
            return [f"gsl_simulation/tab_simulation_projet/tab_{tab}.html"]
        return ["gsl_simulation/simulation_projet_detail.html"]

    def get(self, request, *args, **kwargs):
        self.simulation_projet = SimulationProjet.objects.select_related(
            "simulation",
            "simulation__enveloppe",
            "projet",
            "projet__dossier_ds",
        ).get(id=request.resolver_match.kwargs.get("pk"))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.object.projet.dossier_ds.projet_intitule
        context["breadcrumb_dict"] = {
            "links": [
                {
                    "url": reverse("simulation:simulation-list"),
                    "title": "Mes simulations de programmation",
                },
                {
                    "url": reverse(
                        "simulation:simulation-detail",
                        kwargs={"slug": self.simulation_projet.simulation.slug},
                    ),
                    "title": self.simulation_projet.simulation.title,
                },
            ],
            "current": context["title"],
        }
        context["projet"] = self.simulation_projet.projet
        context["simu"] = self.simulation_projet
        context["enveloppe"] = self.simulation_projet.simulation.enveloppe
        context["dossier"] = self.simulation_projet.projet.dossier_ds
        context["menu_dict"] = PROJET_MENU
        context["projet_form"] = ProjetForm(instance=self.object.projet)

        return context

    def post(self, request, *args, **kwargs):
        return update_simulation_projet(request, self.kwargs["pk"])


# TODO à bouger dans gsl_projet
# TODO à tester
class ProjetForm(ModelForm, DsfrBaseForm):
    AVIS_DETR_CHOICES = [
        (None, "En cours"),  # Remplace "Inconnu" par "En cours"
        (True, "Oui"),
        (False, "Non"),
    ]

    avis_commission_detr = forms.ChoiceField(
        label="Sélectionner l'avis de la commission d'élus DETR :",
        choices=AVIS_DETR_CHOICES,
        required=False,
    )

    BUDGET_VERT_CHOICES = [
        (None, "Non Renseigné"),
        (True, "Oui"),
        (False, "Non"),
    ]

    is_budget_vert = forms.ChoiceField(
        label="Transition écologique", choices=BUDGET_VERT_CHOICES, required=False
    )

    class Meta:
        model = Projet
        fields = [
            "is_in_qpv",
            "is_attached_to_a_crte",
            "avis_commission_detr",
            "is_budget_vert",
        ]


class SimulationProjetForm(ModelForm):
    class Meta:
        model = SimulationProjet
        fields = [
            "status",
        ]


@projet_must_be_in_user_perimetre
@exception_handler_decorator  # TODO voir comment le gérer
@require_POST
def update_simulation_projet(request, pk: int):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    # simulation_form = SimulationProjetForm(request.POST, instance=simulation_projet)
    projet_form = ProjetForm(request.POST, instance=simulation_projet.projet)

    # if simulation_form.is_valid() and projet_form.is_valid():
    if projet_form.is_valid():
        # simulation_form.save()
        projet_form.save()
        return redirect_to_simulation_projet(request, simulation_projet)

    return redirect_to_simulation_projet(
        request, simulation_projet, message_type="error"
    )  # TODO que faire ici ?
