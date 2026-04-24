import json

from django.contrib import messages
from django.db import transaction
from django.http import Http404 as DjangoHttp404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView, UpdateView
from django.views.generic.edit import BaseUpdateView
from django_htmx.http import HttpResponseClientRefresh

from gsl.settings import ALLOWED_HOSTS
from gsl_core.decorators import htmx_only
from gsl_core.exceptions import Http404
from gsl_core.matomo import queue_matomo_event
from gsl_core.matomo_constants import (
    MATOMO_ACTION_CHANGEMENT_STATUT,
    MATOMO_ACTION_CHANGEMENT_STATUT_AVEC_NOTIFICATION_DEMANDE_CONFIRMATION,
    MATOMO_ACTION_CHANGEMENT_STATUT_BULK,
    MATOMO_ACTION_CHANGEMENT_STATUT_CONFIRME,
    MATOMO_ACTION_CHANGEMENT_STATUT_SANS_NOTIFICATION_DEMANDE_CONFIRMATION,
    MATOMO_ACTION_MODIFICATION_ASSIETTE,
    MATOMO_ACTION_MODIFICATION_MONTANT,
    MATOMO_ACTION_MODIFICATION_MONTANTS,
    MATOMO_ACTION_MODIFICATION_TAUX,
    MATOMO_CATEGORY_PROGRAMMATION,
    MATOMO_CATEGORY_SIMULATION,
)
from gsl_core.templatetags.gsl_filters import euro
from gsl_core.view_mixins import OpenHtmxModalMixin
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.importer.dossier import save_one_dossier_from_ds
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.forms import DotationProjetForm, ProjetForm
from gsl_projet.models import DotationProjet, projet_status_from_dotation_statuses
from gsl_projet.utils.projet_page import PROJET_MENU
from gsl_simulation.filters import SimulationProjetFilters
from gsl_simulation.forms import (
    AssietteSingleFieldForm,
    CommentSingleFieldForm,
    DismissProjetForm,
    MontantSingleFieldForm,
    RefuseProjetForm,
    SimulationProjetForm,
    SimulationProjetStatusForm,
    TauxSingleFieldForm,
)
from gsl_simulation.models import (
    BulkStatusJob,
    SimulationProjet,
    SimulationProjetQuerySet,
)
from gsl_simulation.table_columns import SIMULATION_TABLE_COLUMNS
from gsl_simulation.views.bulk_status_job_views import BULK_STATUS_MODAL_ID
from gsl_simulation.views.decorators import (
    exception_handler_decorator,
)


class SimulationTableCellEditMixin(UpdateView):
    model = SimulationProjet
    context_object_name = "simu"
    matomo_action: str = ""

    def get_queryset(self):
        return SimulationProjet.objects.in_user_perimeter(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def _queue_matomo_event(self, name: str):
        if self.matomo_action:
            queue_matomo_event(
                self.request, MATOMO_CATEGORY_SIMULATION, self.matomo_action, name
            )

    def form_valid(self, form):
        try:
            form.save()
        except DsServiceException as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)
        self.object.refresh_from_db()
        self.object.simulation.save(update_fields=["updated_at"])
        self._queue_matomo_event("valide")
        return self.render_success_partial()

    def form_invalid(self, form):
        self._queue_matomo_event("invalide")
        return super().form_invalid(form)

    def _get_projets_queryset_with_filters(self):
        simulation = self.object.simulation
        filterset = SimulationProjetFilters(
            data=self.request.GET or None,
            request=self.request,
            slug=simulation.slug,
        )
        return filterset.qs.filter(
            dotationprojet__simulationprojet__simulation=simulation
        )

    def render_success_partial(self):
        total_amount_granted = self.object.simulation.get_total_amount_granted(
            self._get_projets_queryset_with_filters()
        )

        return render(
            self.request,
            "htmx/projet_update.html",
            {
                "simu": self.object,
                "dotation_projet": self.object.dotation_projet,
                "projet": self.object.projet,
                "status_summary": self.object.simulation.get_projet_status_summary(),
                "total_amount_granted": total_amount_granted,
                "columns": SIMULATION_TABLE_COLUMNS,
                "dotations": DOTATIONS,
            },
        )


class EditAssietteView(SimulationTableCellEditMixin):
    form_class = AssietteSingleFieldForm
    template_name = "gsl_simulation/table_cells/edit_forms/_assiette_edit_form.html"
    matomo_action = MATOMO_ACTION_MODIFICATION_ASSIETTE

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.object.dotation_projet
        kwargs["simulation_projet"] = self.object
        return kwargs


class EditMontantView(SimulationTableCellEditMixin):
    form_class = MontantSingleFieldForm
    template_name = "gsl_simulation/table_cells/edit_forms/_montant_edit_form.html"
    matomo_action = MATOMO_ACTION_MODIFICATION_MONTANT


class EditTauxView(SimulationTableCellEditMixin):
    form_class = TauxSingleFieldForm
    template_name = "gsl_simulation/table_cells/edit_forms/_taux_edit_form.html"
    matomo_action = MATOMO_ACTION_MODIFICATION_TAUX


class EditCommentView(SimulationTableCellEditMixin):
    form_class = CommentSingleFieldForm
    template_name = "gsl_simulation/table_cells/edit_forms/_comment_edit_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.object.projet
        kwargs["comment_number"] = self.kwargs["comment_number"]
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["comment_number"] = self.kwargs["comment_number"]
        return context


class RefreshSimulationRowView(DetailView):
    model = SimulationProjet
    template_name = "includes/_simulation_detail_row.html"

    def get_queryset(self):
        return (
            SimulationProjet.objects.in_user_perimeter(self.request.user)
            .select_related(
                "simulation",
                "simulation__enveloppe",
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
            )
            .prefetch_related("dotation_projet__projet__dotationprojet_set")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        simulation_projet = self.object
        context.update(
            {
                "simu": simulation_projet,
                "dotation_projet": simulation_projet.dotation_projet,
                "projet": simulation_projet.projet,
                "columns": SIMULATION_TABLE_COLUMNS,
                "dotations": DOTATIONS,
            }
        )
        return context


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
    template_name = "gsl_simulation/simulation_projet_detail.html"

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
            queue_matomo_event(
                self.request,
                MATOMO_CATEGORY_PROGRAMMATION,
                MATOMO_ACTION_MODIFICATION_MONTANTS,
                form.instance.dotation_projet.dotation,
            )
        except DsServiceException as e:
            error_msg = f"Une erreur est survenue lors de la mise à jour des informations sur Démarche Numérique. {str(e)}"
            form.add_error(None, error_msg)
            return self.form_invalid(form, with_error_message_intro=False)

        simulation_projet = self.get_object()
        simulation_projet.simulation.save(update_fields=["updated_at"])

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

    def form_valid(self, form: ProjetForm):
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

        # When a dotation is removed, the DotationProjet is deleted,
        # which CASCADE deletes the SimulationProjet. Redirect to the
        # simulation project list instead of the now-deleted detail page.
        if not SimulationProjet.objects.filter(pk=self.object.pk).exists():
            return redirect(
                "simulation:simulation-detail",
                slug=self.object.simulation.slug,
            )

        return redirect_to_same_page_or_to_simulation_detail_by_default(
            self.request,
            self.object,
        )

    def enrich_context_with_invalid_form(self, context, form):
        context["projet_form"] = form


class SimulationProjetDetailView(BaseSimulationProjetView):
    model = SimulationProjet
    form_class = SimulationProjetForm

    def get_queryset(self):
        return super().get_queryset().in_user_perimeter(self.request.user)

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except DjangoHttp404:
            # The SimulationProjet may have been CASCADE-deleted after a
            # DotationProjet deletion (e.g., DN refresh reverting status).
            # Re-raise if the object still exists (e.g. perimeter mismatch).
            if not SimulationProjet.objects.filter(pk=kwargs["pk"]).exists():
                messages.warning(request, "Ce projet n'est plus dans cette simulation.")
                return redirect("simulation:simulation-list")
            raise

    def enrich_context_with_invalid_form(self, context, form):
        context["simulation_projet_form"] = form


def redirect_to_same_page_or_to_simulation_detail_by_default(
    request, simulation_projet
):
    referer = request.headers.get("Referer")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts=ALLOWED_HOSTS
    ):
        return redirect(referer)

    return redirect(
        "simulation:simulation-detail", slug=simulation_projet.simulation.slug
    )


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
        return SimulationProjet.objects.in_user_perimeter(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["status"] = self.kwargs["status"]
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["new_simulation_status"] = self.kwargs["status"]
        return context

    def get_modal_id(self):
        return f"{self.kwargs['status']}-modal-{self.object.pk}"

    def form_valid(self, form):
        try:
            form.save(user=self.request.user)
            self.object.simulation.save(update_fields=["updated_at"])
            messages.info(
                self.request,
                {
                    SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: f"La dotation {self.object.dotation_projet.dotation} est acceptée provisoirement dans cette simulation.",
                    SimulationProjet.STATUS_PROVISIONALLY_REFUSED: f"La dotation {self.object.dotation_projet.dotation} est refusée provisoirement dans cette simulation.",
                    SimulationProjet.STATUS_PROCESSING: f"La demande de financement avec la dotation {self.object.dotation_projet.dotation} est bien repassée en traitement.",
                }[self.kwargs["status"]],
                extra_tags=self.kwargs["status"],
            )
            queue_matomo_event(
                self.request,
                MATOMO_CATEGORY_SIMULATION,
                MATOMO_ACTION_CHANGEMENT_STATUT,
                f"{self.kwargs['status']}",
            )
        except DsServiceException as e:  # rollback the transaction + show error
            messages.error(
                self.request,
                f"{str(e)}",
            )
        return HttpResponseClientRefresh()


@method_decorator(htmx_only, name="dispatch")
@method_decorator(require_POST, name="dispatch")
class BulkSimulationProjetStatusUpdateView(OpenHtmxModalMixin, TemplateView):
    """
    Bulk status change entry point. For transitions that do NOT touch DN
    (pending → pending), commits all rows in a single transaction and triggers
    a page refresh. For transitions that DO touch DN (target = accepted, or at
    least one selected row currently accepted), returns an HTMX confirmation
    modal that chains to the async job flow in `BulkStatusJobStartView`.

    Reuses `SimulationProjetStatusForm.save()` per row so the single-row
    behavior stays authoritative.
    """

    modal_id = BULK_STATUS_MODAL_ID
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        target_status = kwargs["status"]
        if target_status not in BulkStatusJob.ALLOWED_TARGET_STATUSES:
            raise Http404(user_message="Statut de simulation invalide")

        raw_ids = request.POST.get("simulation_projet_ids", "")
        try:
            ids = [int(i) for i in raw_ids.split(",") if i.strip()]
        except ValueError:
            raise Http404(user_message="Identifiants de projets invalides")

        if not ids:
            messages.error(
                request, "Aucun projet sélectionné pour le changement de statut."
            )
            return HttpResponseClientRefresh()

        all_projets = list(
            SimulationProjet.objects.in_user_perimeter(request.user)
            .filter(id__in=ids)
            .select_related(
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
                "simulation",
                "simulation__enveloppe",
            )
        )
        if {sp.id for sp in all_projets} != set(ids):
            raise Http404(
                user_message=(
                    "Un ou plusieurs des projets sélectionnés n'est pas accessible "
                    "(identifiant inconnu ou hors de votre périmètre)."
                )
            )

        if any(sp.dotation_projet.projet.notified_at is not None for sp in all_projets):
            raise Http404(
                user_message=(
                    "Un ou plusieurs des projets sélectionnés a déjà été notifié "
                    "et ne peut plus être modifié."
                )
            )

        needs_dn = self._needs_ds_confirmation(target_status, all_projets)

        if needs_dn and not request.user.ds_id:
            return self._render_simple_modal(
                "htmx/bulk_status_missing_ds_profile_modal.html"
            )

        valid_projets, blockers = self._preflight(all_projets, target_status)

        if not valid_projets:
            return self._render_simple_modal(
                "htmx/bulk_status_nothing_modifiable_modal.html"
            )

        if blockers:
            return self._render_preflight_modal(
                target_status=target_status,
                valid_projets=[sp for sp, _form in valid_projets],
                blockers=blockers,
            )

        if needs_dn:
            return self._render_confirmation_modal(
                target_status, [sp for sp, _form in valid_projets]
            )

        return self._commit_non_dn(request, target_status, valid_projets)

    @staticmethod
    def _preflight(candidate_projets, target_status):
        """
        Split candidates into rows that can transition to `target_status` and
        rows that can't. Reuses `SimulationProjetStatusForm.clean()` (the same
        validation used by the single-row flow) per row.

        Returns `(valid_projets, blockers)` where each entry in `valid_projets`
        is a `(simulation_projet, bound_form)` tuple — the caller that commits
        the transition reuses the already-validated form. Each blocker carries
        only a `reason_code` — the template groups by reason and picks a
        bulk-specific sentence per code.
        """
        valid_projets = []
        blockers = []
        for sp in candidate_projets:
            form = SimulationProjetStatusForm(
                data={}, instance=sp, status=target_status
            )
            if form.is_valid():
                valid_projets.append((sp, form))
                continue

            first = next(
                (err for errs in form.errors.as_data().values() for err in errs),
                None,
            )
            blockers.append(
                {"reason_code": first.code if first and first.code else "invalid"}
            )
        return valid_projets, blockers

    def _commit_non_dn(self, request, target_status, valid_projets):
        with transaction.atomic():
            for _sp, form in valid_projets:
                form.save(user=request.user)

        queue_matomo_event(
            request,
            MATOMO_CATEGORY_SIMULATION,
            MATOMO_ACTION_CHANGEMENT_STATUT_BULK,
            f"{target_status}:{len(valid_projets)}",
        )

        return HttpResponseClientRefresh()

    @staticmethod
    def _needs_ds_confirmation(target_status, simulation_projets):
        if target_status == SimulationProjet.STATUS_ACCEPTED:
            return True
        return any(
            sp.dotation_projet.status == PROJET_STATUS_ACCEPTED
            for sp in simulation_projets
        )

    def _render_confirmation_modal(self, target_status, simulation_projets):
        if not simulation_projets:
            messages.error(
                self.request, "Aucun projet sélectionné pour le changement de statut."
            )
            return HttpResponseClientRefresh()

        self.template_name = "htmx/bulk_status_confirm_modal.html"
        return self.render_to_response(
            self.get_context_data(
                target_status=target_status,
                simulation_projets=simulation_projets,
                simulation_projet_ids=",".join(str(sp.id) for sp in simulation_projets),
            )
        )

    def _render_preflight_modal(self, target_status, valid_projets, blockers):
        self.template_name = "htmx/bulk_status_preflight_modal.html"
        return self.render_to_response(
            self.get_context_data(
                target_status=target_status,
                valid_projets=valid_projets,
                blockers=blockers,
                simulation_projet_ids=",".join(str(sp.id) for sp in valid_projets),
            )
        )

    def _render_simple_modal(self, template_name):
        self.template_name = template_name
        return self.render_to_response(self.get_context_data())


@method_decorator(htmx_only, name="dispatch")
class ProgrammationStatusUpdateView(OpenHtmxModalMixin, UpdateView):
    context_object_name = "simulation_projet"
    new_project_status: str = ""
    acceptance_errors: list = []

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

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        if self.new_project_status in [PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED]:
            queue_matomo_event(
                request,
                MATOMO_CATEGORY_PROGRAMMATION,
                MATOMO_ACTION_CHANGEMENT_STATUT_AVEC_NOTIFICATION_DEMANDE_CONFIRMATION,
                f"{self.kwargs['status']}",
            )

        elif self.new_project_status in [
            PROJET_STATUS_PROCESSING,
            PROJET_STATUS_ACCEPTED,
        ]:
            queue_matomo_event(
                request,
                MATOMO_CATEGORY_PROGRAMMATION,
                MATOMO_ACTION_CHANGEMENT_STATUT_SANS_NOTIFICATION_DEMANDE_CONFIRMATION,
                f"{self.kwargs['status']}",
            )

        self.acceptance_errors = []
        if self.kwargs["status"] == SimulationProjet.STATUS_ACCEPTED:
            validation_form = self.get_form_class()(
                data={},
                instance=self.object,
                status=self.kwargs["status"],
            )
            if not validation_form.is_valid():
                self.acceptance_errors = list(validation_form.non_field_errors())

        # On contourne BaseUpdateView.get() pour éviter un second appel à get_object()
        return super(BaseUpdateView, self).get(request, *args, **kwargs)

    def get_modal_id(self):
        return f"{self.kwargs['status']}-modal-{self.object.pk}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["new_projet_status"] = self.new_project_status
        context["new_simulation_status"] = self.kwargs["status"]
        context["acceptance_errors"] = self.acceptance_errors
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["status"] = self.kwargs["status"]
        return kwargs

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
        if self.acceptance_errors:
            return ["htmx/acceptance_errors_modal.html"]
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
            form.save(user=self.request.user)
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

        self.object.simulation.save(update_fields=["updated_at"])
        message = self.get_success_message()

        messages.success(
            self.request,
            message,
            extra_tags=self.object.projet.status,
        )
        queue_matomo_event(
            self.request,
            MATOMO_CATEGORY_PROGRAMMATION,
            MATOMO_ACTION_CHANGEMENT_STATUT_CONFIRME,
            f"{self.kwargs['status']}",
        )
        return (
            HttpResponseClientRefresh()
        )  # we reload the page without the modal and with the success message
