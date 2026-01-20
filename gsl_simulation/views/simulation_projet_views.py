import json

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest
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
from gsl_core.exceptions import Http404
from gsl_core.templatetags.gsl_filters import euro
from gsl_core.view_mixins import OpenHtmxModalMixin
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier import save_one_dossier_from_ds
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.forms import DotationProjetForm, ProjetForm
from gsl_projet.models import DotationProjet, projet_status_from_dotation_statuses
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.utils.projet_page import PROJET_MENU
from gsl_simulation.forms import (
    DismissProjetForm,
    RefuseProjetForm,
    SimulationProjetForm,
    SimulationProjetStatusForm,
)
from gsl_simulation.models import SimulationProjet, SimulationProjetQuerySet
from gsl_simulation.services.simulation_projet_service import (
    SimulationProjetService,
)
from gsl_simulation.utils import (
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

    def get_template_names(self):
        if "tab" in self.kwargs:
            tab = self.kwargs["tab"]
            if tab not in self.ALLOWED_TABS:
                raise Http404
            return [f"gsl_simulation/tab_simulation_projet/tab_{tab}.html"]
        return ["gsl_simulation/simulation_projet_detail.html"]

    def get_object(self, queryset=None) -> SimulationProjet:
        if not hasattr(self, "_simulation_projet"):
            self._simulation_projet = super().get_object(queryset)
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

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def form_valid(self, form: SimulationProjetForm):
        try:
            form.save()
            messages.success(
                self.request,
                "Les modifications ont été enregistrées avec succès.",
            )
        except DsServiceException as e:
            error_msg = f"Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. {str(e)}"
            form.add_error(None, error_msg)
            return self.form_invalid(form, with_error_message_intro=False)

        simulation_projet = self.get_object()

        return redirect_to_same_page_or_to_simulation_detail_by_default(
            self.request,
            simulation_projet,
        )

    def form_invalid(self, form: SimulationProjetForm, with_error_message_intro=True):
        self.set_main_error_message(form, with_error_message_intro)

        simulation_projet = self.get_object()

        view = SimulationProjetDetailView()
        view.request = self.request
        view.kwargs = {"pk": simulation_projet.id}
        view.object = simulation_projet  # nécessaire pour get_context_data

        view.request = self.request
        view.kwargs = {"pk": simulation_projet.id}
        context = view.get_context_data(object=simulation_projet)

        self.enrich_context_with_invalid_form(context, form)
        return render(
            self.request, "gsl_simulation/simulation_projet_detail.html", context
        )

    def set_main_error_message(self, form, with_error_message_intro=True):
        error_msg = ""
        if with_error_message_intro:
            error_msg += (
                "Une erreur s'est produite lors de la soumission du formulaire."
            )

        if form.non_field_errors():
            # Join errors directly to avoid HTML encoding from as_text()
            error_msg += " ".join(str(error) for error in form.non_field_errors())

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

    def enrich_context_with_invalid_form(self, context, form):
        context["projet_form"] = form


class SimulationProjetDetailView(BaseSimulationProjetView):
    model = SimulationProjet
    form_class = SimulationProjetForm

    ALLOWED_TABS = {"historique"}

    def get_queryset(self):
        return super().get_queryset().in_user_perimeter(self.request.user)

    def enrich_context_with_invalid_form(self, context, form):
        context["simulation_projet_form"] = form


def redirect_to_same_page_or_to_simulation_detail_by_default(
    request, simulation_projet
):
    if request.htmx:
        return render_partial_simulation_projet(request, simulation_projet)

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

    total_amount_granted = simulation_projet.simulation.get_total_amount_granted(
        filtered_projets
    )

    return render(
        request,
        "htmx/projet_update.html",
        {
            "simu": simulation_projet,
            "dotation_projet": simulation_projet.dotation_projet,
            "projet": simulation_projet.projet,
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
            "other_dotation_montants": _get_other_dotation_montants(simulation_projet),
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


def _get_other_dotation_montants(
    simulation_projet: SimulationProjet,
) -> object | None:
    if not simulation_projet.projet.has_double_dotations:
        return None

    other_dotation_projet = DotationProjet.objects.filter(
        projet=simulation_projet.projet,
        dotation=(
            DOTATION_DETR
            if simulation_projet.dotation_projet.dotation == DOTATION_DSIL
            else DOTATION_DSIL
        ),
    ).first()
    montants = {
        "dotation": other_dotation_projet.dotation,
        "assiette": other_dotation_projet.assiette,
        "montant": None,
        "taux": None,
    }

    if hasattr(other_dotation_projet, "programmation_projet"):
        montants["montant"] = other_dotation_projet.programmation_projet.montant
        montants["taux"] = other_dotation_projet.programmation_projet.taux

    return montants


@method_decorator(htmx_only, name="dispatch")
class SimulationProjetStatusUpdateView(OpenHtmxModalMixin, UpdateView):
    """
    This form handles status update of a SimulationProjet for all simulation only statys:
    STATUS_PROCESSING, and both STATUS_PROVISIONNALY_*

    Depending on previous status, it can be directly POSTed or GETed to display and
    HTMX confirmation modal. Wether it's a POST or a GET, is handled by
    `gsl_simulation.templatetags.simulation_filters`
    """

    model = SimulationProjet
    form_class = SimulationProjetStatusForm
    template_name = "htmx/go_back_to_simulation_state_modal.html"

    def dispatch(self, request, *args, **kwargs):
        if self.kwargs["status"] not in SimulationProjet.SIMULATION_PENDING_STATUSES:
            raise Http404(user_message="Statut de simulation invalide")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return SimulationProjet.objects.in_user_perimeter(self.request.user).exclude(
            dotation_projet__projet__notified_at__isnull=False
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["new_simulation_status"] = self.kwargs["status"]
        return context

    def get_modal_id(self):
        return f"{self.kwargs['status']}-modal-{self.object.pk}"

    def form_valid(self, form):
        try:
            form.save(status=self.kwargs["status"], user=self.request.user)
            messages.info(
                self.request,
                {
                    SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: "Le projet est accepté provisoirement dans cette simulation.",
                    SimulationProjet.STATUS_PROVISIONALLY_REFUSED: "Le projet est refusé provisoirement dans cette simulation.",
                    SimulationProjet.STATUS_PROCESSING: f"La demande de financement avec la dotation {self.object.dotation_projet.dotation} est bien repassée en traitement.",
                }[self.kwargs["status"]],
                extra_tags=self.kwargs["status"],
            )
        except DsServiceException as e:  # rollback the transaction + show error
            messages.error(
                self.request,
                f"{str(e)}",
            )
        return HttpResponseClientRefresh()


@method_decorator(htmx_only, name="dispatch")
class ProgrammationStatusUpdateView(OpenHtmxModalMixin, UpdateView):
    context_object_name = "simulation_projet"
    new_project_status: str = ""

    def dispatch(self, request, *args, **kwargs):
        if (
            self.kwargs["status"] not in (s[0] for s in SimulationProjet.STATUS_CHOICES)
            or self.kwargs["status"] in SimulationProjet.SIMULATION_PENDING_STATUSES
        ):
            raise Http404(user_message="Statut de simulation invalide")

        try:
            return super().dispatch(request, *args, **kwargs)
        except DsServiceException as e:
            messages.error(
                self.request,
                str(e),
            )
            return HttpResponseClientRefresh()  # we reload the page without the modal

    def get_object(self, queryset=None) -> SimulationProjet:
        obj = super().get_object(queryset)
        save_one_dossier_from_ds(obj.projet.dossier_ds)
        self.new_project_status = projet_status_from_dotation_statuses(
            (
                self.kwargs["status"],
                *(d.status for d in obj.dotation_projet.other_dotations),
            )
        )
        return obj

    def get_modal_id(self):
        return f"{self.kwargs['status']}-modal-{self.object.pk}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["new_projet_status"] = self.new_project_status
        context["new_simulation_status"] = self.kwargs["status"]
        return context

    def get_form_class(self):
        if self.new_project_status == PROJET_STATUS_REFUSED:
            return RefuseProjetForm

        if self.new_project_status == PROJET_STATUS_DISMISSED:
            return DismissProjetForm

        return SimulationProjetStatusForm

    def get_template_names(self):
        if self.request.user.ds_id not in [
            i.ds_id for i in self.object.dossier.ds_instructeurs.all()
        ]:
            return ["htmx/not_instructeur_error.html"]
        if self.new_project_status in [
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_ACCEPTED,
        ]:
            return ["htmx/notify_later_confirmation_modal.html"]

        if self.new_project_status in [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED]:
            return ["htmx/notify_project_confirmation_modal.html"]

        raise ValueError(f"Invalid status: {self.new_project_status}")

    def get_queryset(self) -> SimulationProjetQuerySet:
        return (
            SimulationProjet.objects.in_user_perimeter(self.request.user)
            # On exclut les simulations-projet liés à une programmation-projet déjà notifiée.
            .exclude(dotation_projet__projet__notified_at__isnull=False)
            .select_related(
                "simulation",
                "simulation__enveloppe",
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
            )
            .prefetch_related("dotation_projet__projet__dossier_ds__ds_instructeurs")
        )

    def get_success_message(self):
        SIMU_PROJET_STATUS_TO_MESSAGE = {
            SimulationProjet.STATUS_ACCEPTED: f"La demande de financement avec la dotation {self.object.enveloppe.dotation} a bien été acceptée avec un montant de {euro(self.object.montant, 2)}.",
            SimulationProjet.STATUS_REFUSED: f"La demande de financement avec la dotation {self.object.enveloppe.dotation} a bien été refusée.",
            SimulationProjet.STATUS_DISMISSED: f"La demande de financement avec la dotation {self.object.enveloppe.dotation} a bien été classée sans suite.",
        }

        message = SIMU_PROJET_STATUS_TO_MESSAGE[self.kwargs["status"]]

        ds_message = ""

        if self.new_project_status in [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED]:
            ds_message = " Le dossier a bien été mis à jour sur Démarche Numérique."

            if (
                self.new_project_status == PROJET_STATUS_DISMISSED
                and self.kwargs["status"] == SimulationProjet.STATUS_REFUSED
            ):
                other_dotation = self.object.dotation_projet.other_dotations[0].dotation
                ds_message = f" Sachant que la dotation {other_dotation} a été classée sans suite, le dossier a bien été classé sans suite sur Démarche Numérique."

        return message + ds_message

    def form_valid(self, form):
        try:
            form.save(status=self.kwargs["status"], user=self.request.user)
        except DsServiceException as e:
            if self.get_form_class() == SimulationProjetStatusForm:
                # If the form is SimulationProjetStatusForm, we have no modal to display the error in, so we raise
                # the exception directly so it is handled in dispatch
                raise e

            form.add_error(
                None,
                f"Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. {str(e)}",
            )
            return super().form_invalid(form)

        message = self.get_success_message()

        messages.success(
            self.request,
            message,
            extra_tags=self.object.projet.status,
        )
        return (
            HttpResponseClientRefresh()
        )  # we reload the page without the modal and with the success message
