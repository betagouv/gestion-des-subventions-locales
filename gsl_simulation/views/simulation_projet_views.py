import json

from django.contrib import messages
from django.http import Http404, HttpRequest
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView

from gsl.settings import ALLOWED_HOSTS
from gsl_projet.forms import DotationProjetForm, ProjetForm
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.utils.projet_page import PROJET_MENU
from gsl_simulation.forms import SimulationProjetForm
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.simulation_projet_service import (
    SimulationProjetService,
)
from gsl_simulation.services.simulation_service import SimulationService
from gsl_simulation.utils import (
    add_simulation_projet_status_success_message,
    replace_comma_by_dot,
)
from gsl_simulation.views.decorators import (
    exception_handler_decorator,
    projet_must_be_in_user_perimetre,
)
from gsl_simulation.views.mixins import CorrectUserPerimeterRequiredMixin
from gsl_simulation.views.simulation_views import SimulationDetailView


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_taux_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    new_taux = replace_comma_by_dot(request.POST.get("taux"))
    DotationProjetService.validate_taux(new_taux)
    SimulationProjetService.update_taux(simulation_projet, new_taux)
    return redirect_to_same_page_or_to_simulation_detail_by_default(
        request, simulation_projet
    )


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_montant_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    new_montant = replace_comma_by_dot(request.POST.get("montant"))
    DotationProjetService.validate_montant(
        new_montant, simulation_projet.dotation_projet
    )
    SimulationProjetService.update_montant(simulation_projet, new_montant)
    return redirect_to_same_page_or_to_simulation_detail_by_default(
        request, simulation_projet
    )


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
    return redirect_to_same_page_or_to_simulation_detail_by_default(
        request, updated_simulation_projet, status
    )


@projet_must_be_in_user_perimetre
@exception_handler_decorator
@require_POST
def patch_dotation_projet(request, pk):
    simulation_projet = get_object_or_404(SimulationProjet, id=pk)
    form = DotationProjetForm(
        request.POST,
        instance=simulation_projet.dotation_projet,
    )
    if form.is_valid():
        form.save()
        messages.success(
            request,
            "Les modifications ont été enregistrées avec succès.",
        )
        return redirect_to_same_page_or_to_simulation_detail_by_default(
            request, simulation_projet
        )

    messages.error(
        request,
        "Une erreur s'est produite lors de la soumission du formulaire.",
    )

    return redirect_to_same_page_or_to_simulation_detail_by_default(
        request, simulation_projet
    )


class ProjetFormView(UpdateView):
    model = SimulationProjet
    form_class = ProjetForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        self.simulation_projet: SimulationProjet = self.get_object()
        kwargs.update(
            {"instance": self.simulation_projet.projet, "user": self.request.user}
        )
        return kwargs

    def form_valid(self, form: SimulationProjetForm):
        _, error_msg = form.save()
        if error_msg:
            messages.error(self.request, error_msg)
        else:
            messages.success(
                self.request,
                "Les modifications ont été enregistrées avec succès.",
            )

        # TODO use success_url
        return redirect_to_same_page_or_to_simulation_detail_by_default(
            self.request,
            self.simulation_projet,
        )

    def form_invalid(self, form: SimulationProjetForm):
        error_msg = "Une erreur s'est produite lors de la soumission du formulaire."
        if form.non_field_errors():
            # remove the '* ' at the beginning
            error_msg += form.non_field_errors().as_text()[1:]

        messages.error(self.request, error_msg)

        simulation_projet = self.get_object()

        view = SimulationProjetDetailView()
        view.request = self.request
        view.kwargs = {"pk": simulation_projet.id}
        view.object = simulation_projet  # nécessaire pour get_context_data

        view.request = self.request
        view.kwargs = {"pk": simulation_projet.id}
        context = view.get_context_data(object=simulation_projet)
        context["projet_form"] = form
        return render(
            self.request, "gsl_simulation/simulation_projet_detail.html", context
        )


class SimulationProjetDetailView(
    CorrectUserPerimeterRequiredMixin, UpdateView
):  # TODO check if CorrectUserPerimeterRequiredMixin is used
    model = SimulationProjet
    form_class = SimulationProjetForm

    ALLOWED_TABS = {"historique"}

    def get_template_names(self):
        if "tab" in self.kwargs:
            tab = self.kwargs["tab"]
            if tab not in self.ALLOWED_TABS:
                raise Http404
            return [f"gsl_simulation/tab_simulation_projet/tab_{tab}.html"]
        return ["gsl_simulation/simulation_projet_detail.html"]

    def get_object(self, queryset=None):
        if not hasattr(self, "_simulation_projet"):
            self._simulation_projet = _get_view_simulation_projet_from_pk(
                self.kwargs.get("pk")
            )
        return self._simulation_projet

    def get_context_data(self, with_specific_info_for_main_tab=True, **kwargs):
        context = super().get_context_data(**kwargs)
        simulation_projet = self.get_object()
        _enrich_simulation_projet_context_with_generic_info_for_all_tabs(
            context, simulation_projet
        )

        if with_specific_info_for_main_tab:
            _enrich_simulation_projet_context_with_specific_info_for_main_tab(
                context, simulation_projet
            )

        context["simulation_projet_form"] = self.get_form()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def form_valid(self, form: SimulationProjetForm):
        self.object, error_msg = form.save()
        if error_msg:
            messages.error(self.request, error_msg)
        else:
            messages.success(
                self.request,
                "Les modifications ont été enregistrées avec succès.",
            )

        # TODO use success_url
        return redirect_to_same_page_or_to_simulation_detail_by_default(
            self.request,
            self.object,
        )

    def form_invalid(self, form: SimulationProjetForm):
        error_msg = "Une erreur s'est produite lors de la soumission du formulaire."
        if form.non_field_errors():
            # remove the '* ' at the beginning
            error_msg += form.non_field_errors().as_text()[1:]

        messages.error(self.request, error_msg)  # TODO test

        return super().form_invalid(form)

    # def get_success_url(self):
    #     return redirect_to_same_page_or_to_simulation_detail_by_default(
    #         self.request, self.object
    #     )


# TODO make this function render an url ?
# TODO rename function ?
# TODO update functions which call it ?
def redirect_to_same_page_or_to_simulation_detail_by_default(
    request, simulation_projet, message_type: str | None = None
):
    if request.htmx:
        return render_partial_simulation_projet(request, simulation_projet)

    if message_type is not None:
        add_simulation_projet_status_success_message(
            request, message_type, simulation_projet
        )

    referer = request.headers.get("Referer")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts=ALLOWED_HOSTS
    ):
        return redirect(referer)

    return redirect(
        "simulation:simulation-detail", slug=simulation_projet.simulation.slug
    )


def render_partial_simulation_projet(request, simulation_projet):
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
            "dotation_projet": simulation_projet.dotation_projet,
            "projet": simulation_projet.projet,
            "available_states": SimulationProjet.STATUS_CHOICES,
            "status_summary": simulation_projet.simulation.get_projet_status_summary(),
            "total_amount_granted": total_amount_granted,
            "filter_params": filter_params,
        },
    )


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


def _enrich_simulation_projet_context_with_specific_info_for_main_tab(
    context: dict, simulation_projet: SimulationProjet
):
    if context.get("projet_form", None) is None:
        projet_form = ProjetForm(instance=simulation_projet.projet)
        context["projet_form"] = projet_form

    simulation_projet_form = SimulationProjetForm(instance=simulation_projet)
    dotation_field = projet_form.fields.get("dotations")
    context.update(
        {
            "enveloppe": simulation_projet.simulation.enveloppe,
            "menu_dict": PROJET_MENU,
            "simulation_projet_form": simulation_projet_form,
            "dotation_projet_form": DotationProjetForm(
                instance=simulation_projet.dotation_projet,
            ),
            "initial_dotations": json.dumps(dotation_field.initial)
            if dotation_field
            else [],
            "other_dotation_simu": _get_other_dotation_simulation_projet(
                simulation_projet
            ),
            "dotation_projets": simulation_projet.projet.dotationprojet_set.all(),
        }
    )


def _enrich_simulation_projet_context_with_generic_info_for_all_tabs(
    context: dict, simulation_projet: SimulationProjet
):
    title = simulation_projet.projet.dossier_ds.projet_intitule
    context.update(
        {
            "title": title,
            "breadcrumb_dict": {
                "links": [
                    {
                        "url": reverse("simulation:simulation-list"),
                        "title": "Mes simulations de programmation",
                    },
                    {
                        "url": reverse(
                            "simulation:simulation-detail",
                            kwargs={"slug": simulation_projet.simulation.slug},
                        ),
                        "title": simulation_projet.simulation.title,
                    },
                ],
                "current": title,
            },
            "simu": simulation_projet,
            "projet": simulation_projet.projet,
            "dotation_projet": simulation_projet.dotation_projet,
            "dossier": simulation_projet.projet.dossier_ds,
        }
    )


def _get_view_simulation_projet_from_pk(pk: int):
    return (
        SimulationProjet.objects.select_related(
            "simulation",
            "simulation__enveloppe",
            "dotation_projet",
            "dotation_projet__projet",
            "dotation_projet__projet__dossier_ds",
        )
        .prefetch_related("dotation_projet__projet__dotationprojet_set")
        .get(id=pk)
    )


def _get_other_dotation_simulation_projet(
    simulation_projet: SimulationProjet,
) -> SimulationProjet | None:
    if not simulation_projet.projet.has_double_dotations:
        return None

    # Get the most recent simulation projet with the same projet but different dotation
    return (
        SimulationProjet.objects.filter(
            dotation_projet__projet=simulation_projet.projet,
        )
        .exclude(dotation_projet__dotation=simulation_projet.dotation_projet.dotation)
        .order_by("-updated_at")
        .first()
    )
