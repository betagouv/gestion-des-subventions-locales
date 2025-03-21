from django.http import Http404, HttpRequest
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from gsl.settings import ALLOWED_HOSTS
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


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_avis_commission_detr_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    avis_commission_detr = request.POST.get("avis_commission_detr")

    if avis_commission_detr not in ("None", "True", "False"):
        raise ValueError("Invalid avis_commission_detr")

    if avis_commission_detr == "None":
        new_value = None
    elif avis_commission_detr == "True":
        new_value = True
    else:
        new_value = False

    simulation_projet.projet.avis_commission_detr = new_value
    simulation_projet.projet.save()
    return redirect_to_simulation_projet(request, simulation_projet)


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_is_qpv_and_is_attached_to_a_crte_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    is_in_qpv = request.POST.get("is_in_qpv") == "on"
    is_attached_to_a_crte = request.POST.get("is_attached_to_a_crte") == "on"

    simulation_projet.projet.is_in_qpv = is_in_qpv
    simulation_projet.projet.is_attached_to_a_crte = is_attached_to_a_crte
    simulation_projet.projet.save()
    return redirect_to_simulation_projet(request, simulation_projet)


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

        return context
