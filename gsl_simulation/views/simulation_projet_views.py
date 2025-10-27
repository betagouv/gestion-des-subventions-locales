import json

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponseBadRequest
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import resolve, reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView
from django_htmx.http import HttpResponseClientRefresh

from gsl.settings import ALLOWED_HOSTS
from gsl_core.decorators import htmx_only
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier import save_one_dossier_from_ds
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.forms import DotationProjetForm, ProjetForm
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.utils.projet_page import PROJET_MENU
from gsl_simulation.forms import (
    DismissProjetForm,
    RefuseProjetForm,
    SimulationProjetForm,
)
from gsl_simulation.models import SimulationProjet, SimulationProjetQuerySet
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
)
from gsl_simulation.views.simulation_views import SimulationDetailView


@exception_handler_decorator
@require_POST
def patch_taux_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(
        SimulationProjet.objects.in_user_perimeter(request.user), id=pk
    )
    new_taux = replace_comma_by_dot(request.POST.get("taux"))
    try:
        with transaction.atomic():
            DotationProjetService.validate_taux(new_taux)
            SimulationProjetService.update_taux(
                simulation_projet, new_taux, request.user
            )
    except (ValueError, DsServiceException) as e:
        messages.error(
            request,
            "Une erreur est survenue lors de la mise à jour du taux. " + str(e),
        )
        simulation_projet = SimulationProjet.objects.get(pk=simulation_projet.pk)

    return redirect_to_same_page_or_to_simulation_detail_by_default(
        request, simulation_projet
    )


@exception_handler_decorator
@require_POST
def patch_montant_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(
        SimulationProjet.objects.in_user_perimeter(request.user), id=pk
    )
    new_montant = replace_comma_by_dot(request.POST.get("montant"))
    try:
        with transaction.atomic():
            DotationProjetService.validate_montant(
                new_montant, simulation_projet.dotation_projet
            )
            SimulationProjetService.update_montant(
                simulation_projet, new_montant, user=request.user
            )
    except (ValueError, DsServiceException) as e:
        messages.error(
            request,
            "Une erreur est survenue lors de la mise à jour du montant. " + str(e),
        )
        simulation_projet = SimulationProjet.objects.get(pk=simulation_projet.pk)

    return redirect_to_same_page_or_to_simulation_detail_by_default(
        request, simulation_projet
    )


@exception_handler_decorator
@require_POST
def patch_status_simulation_projet(request, pk):
    simulation_projet = get_object_or_404(
        SimulationProjet.objects.in_user_perimeter(request.user), id=pk
    )
    status = request.POST.get("status")

    if status in [SimulationProjet.STATUS_REFUSED, SimulationProjet.STATUS_DISMISSED]:
        return HttpResponseBadRequest(
            "This endpoint is not for refused projects anymore (you need to fill the form)."
        )

    if (
        status == SimulationProjet.STATUS_ACCEPTED
        and bool(simulation_projet.dotation_projet.assiette) is False
    ):
        messages.error(
            request,
            "Impossible d'accepter le projet car l'assiette lié à cette dotation n'est pas renseignée.",
        )
        return redirect_to_same_page_or_to_simulation_detail_by_default(
            request, simulation_projet
        )

    if status not in dict(SimulationProjet.STATUS_CHOICES).keys():
        raise ValueError("Invalid status")

    try:
        programmation_projet = simulation_projet.dotation_projet.programmation_projet
        if programmation_projet.notified_at:
            raise ValueError("Notified projet status cannot be changed.")
    except ProgrammationProjet.DoesNotExist:
        pass

    try:
        with transaction.atomic():
            updated_simulation_projet = SimulationProjetService.update_status(
                simulation_projet, status, request.user
            )

    except DsServiceException as e:  # rollback the transaction + show error
        messages.error(
            request,
            f"{str(e)}",
        )
        return redirect_to_same_page_or_to_simulation_detail_by_default(
            request, simulation_projet
        )
    return redirect_to_same_page_or_to_simulation_detail_by_default(
        request, updated_simulation_projet, status
    )


@exception_handler_decorator
@require_POST
def patch_dotation_projet(request, pk):
    simulation_projet = get_object_or_404(
        SimulationProjet.objects.in_user_perimeter(request.user), id=pk
    )
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


class BaseSimulationProjetView(UpdateView):
    form_class = SimulationProjetForm

    def get_queryset(self) -> SimulationProjetQuerySet:
        return (
            super()
            .get_queryset()
            .select_related(
                "simulation",
                "simulation__enveloppe",
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
            )
            .prefetch_related("dotation_projet__projet__dotationprojet_set")
        )

    def get_object(self, queryset=None) -> SimulationProjet:
        if not hasattr(self, "_simulation_projet"):
            self._simulation_projet = super().get_object(queryset)
        return self._simulation_projet

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
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
        simulation_projet = self.get_object()

        return redirect_to_same_page_or_to_simulation_detail_by_default(
            self.request,
            simulation_projet,
        )

    def set_main_error_message(self, form):
        error_msg = "Une erreur s'est produite lors de la soumission du formulaire."
        if form.non_field_errors():
            # remove the '* ' at the beginning
            error_msg += form.non_field_errors().as_text()[1:]

        messages.error(self.request, error_msg)


class ProjetFormView(BaseSimulationProjetView):
    model = SimulationProjet
    form_class = ProjetForm

    def get_queryset(self):
        return super().get_queryset().in_user_perimeter(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        simulation_projet = self.get_object()
        kwargs.update({"instance": simulation_projet.projet})
        return kwargs

    def form_invalid(self, form: SimulationProjetForm):
        self.set_main_error_message(form)

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


class SimulationProjetDetailView(BaseSimulationProjetView):
    model = SimulationProjet
    form_class = SimulationProjetForm

    ALLOWED_TABS = {"historique"}

    def get_queryset(self):
        return super().get_queryset().in_user_perimeter(self.request.user)

    def get_template_names(self):
        if "tab" in self.kwargs:
            tab = self.kwargs["tab"]
            if tab not in self.ALLOWED_TABS:
                raise Http404
            return [f"gsl_simulation/tab_simulation_projet/tab_{tab}.html"]
        return ["gsl_simulation/simulation_projet_detail.html"]

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

        return context

    def form_invalid(self, form: SimulationProjetForm):
        self.set_main_error_message(form)

        return render(
            self.request,
            self.get_template_names(),
            self.get_context_data(simulation_projet_form=form),
        )


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

    if context.get("simulation_projet_form", None) is None:
        simulation_projet_form = SimulationProjetForm(instance=simulation_projet)
        context["simulation_projet_form"] = simulation_projet_form

    dotation_field = projet_form.fields.get("dotations")
    context.update(
        {
            "enveloppe": simulation_projet.simulation.enveloppe,
            "menu_dict": PROJET_MENU,
            "dotation_projet_form": DotationProjetForm(
                instance=simulation_projet.dotation_projet,
            ),
            "initial_dotations": (
                json.dumps(dotation_field.initial) if dotation_field else []
            ),
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


@method_decorator(htmx_only, name="dispatch")
class RefuseOrDismissProjetModalBaseView(UpdateView):
    context_object_name = "simulation_projet"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        save_one_dossier_from_ds(obj.projet.dossier_ds)
        return obj

    def get_template_names(self):
        if self.request.user.ds_id not in [
            i.ds_id for i in self.object.dossier.ds_instructeurs.all()
        ]:
            return ["htmx/not_instructeur_error.html"]
        return [self.template_name]

    def get_queryset(self):
        return (
            SimulationProjet.objects.in_user_perimeter(self.request.user)
            # On exclut les simulations-projet liés à une programmation-projet déjà notifiée.
            .exclude(dotation_projet__programmation_projet__notified_at__isnull=False)
            .select_related(
                "simulation",
                "simulation__enveloppe",
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
            )
            .prefetch_related("dotation_projet__projet__dossier_ds__ds_instructeurs")
        )

    def form_valid(self, form):
        try:
            form.save(user=self.request.user)
        except DsServiceException as e:
            form.add_error(
                None,
                f"Une erreur est survenue lors de l'envoi à Démarche Simplifiées. {str(e)}",
            )
            return super().form_invalid(form)

        messages.success(
            self.request, self.success_message, extra_tags=self.object.projet.status
        )
        return (
            HttpResponseClientRefresh()
        )  # we reload the page without the modal and with the success message


class RefuseProjetModalView(RefuseOrDismissProjetModalBaseView):
    template_name = "htmx/refuse_confirmation_form.html"
    form_class = RefuseProjetForm
    success_message = "Le projet a bien été refusé sur Démarches Simplifiées."


class DismissProjetModalView(RefuseOrDismissProjetModalBaseView):
    template_name = "htmx/dismiss_confirmation_form.html"
    form_class = DismissProjetForm
    success_message = (
        "Le projet a bien été classé sans suite sur Démarches Simplifiées."
    )
