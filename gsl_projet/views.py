import json

from django.contrib import messages
from django.db.models import (
    Case,
    DecimalField,
    F,
    IntegerField,
    Max,
    Prefetch,
    Q,
    Sum,
    Value,
    When,
)
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)
from django_filters.views import FilterView
from django_htmx.http import HttpResponseClientRedirect

from gsl.chorus.models import SuiviFinancier
from gsl.chorus.utils import par_dotation
from gsl.historique.models import ProjetAction
from gsl_core.decorators import htmx_only
from gsl_core.models import Perimetre
from gsl_core.view_mixins import (
    FilterSkiplinksMixin,
    OpenHtmxModalMixin,
    SafeRedirectMixin,
)
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    CategorieDsil,
    Cofinancement,
    ProjetContractualisation,
    ProjetZonage,
)
from gsl_projet.forms import (
    ProjetCommentForm,
    ProjetForm,
    ProjetNoteForm,
    ProjetRevertToProcessingForm,
)
from gsl_projet.models import ProjetNote
from gsl_projet.utils.django_filters_custom_widget import CustomSelectWidget
from gsl_projet.utils.projet_filters import (
    ORDERING_MAP,
    ProjetFilters,
    ProjetOrderingFilter,
)
from gsl_projet.utils.projet_page import PROJET_MENU, get_projet_go_back_context
from gsl_projet.utils.utils import get_comment_cards
from gsl_simulation.forms import SimulationProjetForm
from gsl_simulation.models import SimulationProjet

from .models import Projet
from .table_columns import PROJET_TABLE_COLUMNS, SANS_PIECES_SKIP_KEYS


class BaseProjetDetailView(DetailView):
    model = Projet
    pk_url_kwarg = "projet_id"
    context_object_name = "projet"
    http_method_names = ["get"]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Projet.objects.all()
        return Projet.objects.for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_base_projet_context(self.object, self.request))
        return context

    @staticmethod
    def get_base_projet_context(projet, request):
        dotation_projets = sorted(
            projet.dotationprojet_set.all(), key=lambda dp: dp.dotation
        )
        return {
            "title": projet.dossier_ds.projet_intitule,
            "dossier": projet.dossier_ds,
            "dotation_projets": dotation_projets,
            "extra_skiplinks": [{"link": "#projet-panel", "label": "Détail"}],
            **get_projet_go_back_context(request),
        }


class ProjetDetailView(BaseProjetDetailView):
    template_name = "gsl_projet/projet.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projet_form = self._build_projet_form()
        dotation_field = projet_form.fields.get("dotations")

        context.update(
            {
                "menu_dict": PROJET_MENU,
                "projet_form": projet_form,
                "initial_dotations": (
                    json.dumps(dotation_field.initial) if dotation_field else "[]"
                ),
            }
        )
        return context

    def _build_projet_form(self):
        session_key = f"projet_errors_{self.object.pk}"
        if session_key in self.request.session:
            form_data = QueryDict(self.request.session.pop(session_key))
            form = ProjetForm(
                data=form_data, instance=self.object, user=self.request.user
            )
            form.is_valid()
            return form
        return ProjetForm(instance=self.object)


class ProjetSimulationsView(BaseProjetDetailView):
    template_name = "gsl_projet/projet/tab_simulations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        projet = self.object
        all_qs = SimulationProjet.objects.filter(
            dotation_projet__projet=projet
        ).select_related(
            "simulation",
            "simulation__enveloppe",
            "dotation_projet",
            "dotation_projet__projet",
            "dotation_projet__projet__dossier_ds",
        )

        dotation_filter = self.request.GET.get("dotation", "")
        filtered_qs = all_qs.order_by("-simulation__created_at")
        if dotation_filter in ("DETR", "DSIL"):
            filtered_qs = filtered_qs.filter(dotation_projet__dotation=dotation_filter)

        simulation_projets_with_forms = []
        for sp in filtered_qs:
            form_id = f"simulation-card-form-{sp.pk}"
            form = SimulationProjetForm(instance=sp, prefix=form_id)
            for field in ("assiette", "montant", "taux"):
                if field in form.fields:
                    form.fields[field].widget.attrs["form"] = form_id
            simulation_projets_with_forms.append((sp, form, form_id))

        context["simulation_projets_with_forms"] = simulation_projets_with_forms
        context["dotation_filter"] = dotation_filter
        return context


class ProjetHistoriqueView(BaseProjetDetailView):
    template_name = "gsl_projet/projet/tab_historique.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Une notification déclenchée par DN et le changement de statut qui
        # l'accompagne partagent le même created_at (cf.
        # DotationProjetService._create_notified_projet_action_from_dossier_treatment) ;
        # on affiche alors la notification au-dessus du changement de statut.
        display_priority = Case(
            When(action_type=ProjetAction.TYPE_NOTIFIED, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
        context["actions"] = (
            self.object.actions.select_related("actor")
            .annotate(_display_priority=display_priority)
            .order_by("-created_at", "_display_priority")
        )
        return context


class ProjetSuiviFinancierView(BaseProjetDetailView):
    template_name = "gsl_projet/projet/tab_suivi_financier.html"

    def get_queryset(self):
        return super().get_queryset().with_at_least_one_treated_dotation()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["par_dotation"] = par_dotation(self.object)
        context["suivi_date"] = SuiviFinancier.objects.aggregate(
            date=Max("date_transaction")
        )["date"]
        return context


class ProjetNotesContextMixin:
    """Contexte de l'onglet "Notes", partagé entre son affichage
    (ProjetNotesView) et son formulaire d'ajout, qui doit pouvoir réafficher
    ce même onglet en cas d'erreur de validation (ProjetNoteCreateView)."""

    @staticmethod
    def get_notes_context(projet):
        return {
            "projet_notes": projet.notes.all(),
            "comment_cards": get_comment_cards(projet),
            "projet_note_form": ProjetNoteForm(),
        }


class ProjetNotesView(ProjetNotesContextMixin, BaseProjetDetailView):
    template_name = "gsl_projet/projet/tab_notes.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_notes_context(self.object))
        return context


class ProjetCommentUpdateView(SafeRedirectMixin, UpdateView):
    model = Projet
    form_class = ProjetCommentForm
    pk_url_kwarg = "projet_id"
    http_method_names = ["post"]

    def get_queryset(self):
        return Projet.objects.active().for_user(self.request.user)

    def get_success_url(self):
        return reverse("projet:get-projet-notes", kwargs={"projet_id": self.object.pk})

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, "Le commentaire a été enregistré avec succès.")
        return redirect(self.get_safe_redirect_url(fallback=self.get_success_url()))

    def form_invalid(self, form):
        return redirect(self.get_safe_redirect_url(fallback=self.get_success_url()))


def _redirect_to_referer_or_projet(request, projet):
    referer = request.headers.get("Referer")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts=request.get_host()
    ):
        return redirect(referer)
    return redirect("projet:get-projet", projet_id=projet.pk)


class ProjetUpdateView(BaseProjetDetailView, UpdateView):
    form_class = ProjetForm
    http_method_names = ["post"]

    def get_queryset(self):
        return Projet.objects.active().for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        try:
            form.save()
            messages.success(
                self.request,
                "Les modifications ont été enregistrées avec succès.",
            )
        except DsServiceException as e:
            messages.error(
                self.request,
                f"Une erreur est survenue lors de la mise à jour sur Démarche Numérique. {e}",
            )
        return _redirect_to_referer_or_projet(self.request, self.object)

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Une erreur s'est produite lors de la soumission du formulaire.",
        )
        for error in form.non_field_errors():
            messages.error(self.request, error)
        self.request.session[f"projet_errors_{self.object.pk}"] = (
            self.request.POST.urlencode()
        )
        return _redirect_to_referer_or_projet(self.request, self.object)


@method_decorator(htmx_only, name="dispatch")
class ProjetRevertToProcessingView(OpenHtmxModalMixin, UpdateView):
    model = Projet
    form_class = ProjetRevertToProcessingForm
    template_name = "htmx/revert_to_processing_modal.html"
    pk_url_kwarg = "projet_id"

    def get_queryset(self):
        return Projet.objects.for_user(self.request.user).filter(
            notified_at__isnull=False
        )

    def get_modal_id(self):
        return f"revert-to-processing-modal-{self.object.pk}"

    def form_valid(self, form):
        try:
            form.save(user=self.request.user)
            messages.info(
                self.request,
                "Le projet est bien repassé en traitement sur Démarche Numérique.",
            )
        except DsServiceException as e:
            messages.error(self.request, str(e))
        return HttpResponseClientRedirect(
            self.request.headers.get("HX-Current-URL", self.request.path)
        )


class ProjetNoteCreateView(ProjetNotesContextMixin, CreateView):
    model = ProjetNote
    form_class = ProjetNoteForm
    http_method_names = ["post"]

    def form_valid(self, form):
        projet = get_object_or_404(
            Projet.objects.active().for_user(self.request.user),
            pk=self.kwargs["projet_id"],
        )
        note = form.save(commit=False)
        note.projet = projet
        note.created_by = self.request.user
        note.save()
        self.object = note
        messages.success(self.request, "La note a été ajoutée avec succès.")
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        error_messages = (
            "Une erreur s'est produite lors de la soumission du formulaire."
        )
        for error in form.non_field_errors():
            error_messages += f" {error}"

        messages.error(
            self.request,
            error_messages,
        )
        projet = get_object_or_404(
            Projet.objects.active().for_user(self.request.user),
            pk=self.kwargs["projet_id"],
        )
        context = {
            "projet": projet,
            **BaseProjetDetailView.get_base_projet_context(projet, self.request),
            **self.get_notes_context(projet),
            "projet_note_form": form,
        }
        return TemplateResponse(
            self.request,
            ProjetNotesView.template_name,
            context,
            status=200,
        )

    def get_success_url(self):
        referer = self.request.headers.get("Referer")
        if referer and url_has_allowed_host_and_scheme(
            referer, allowed_hosts=self.request.get_host()
        ):
            return referer
        return reverse(
            "projet:get-projet-notes", kwargs={"projet_id": self.object.projet.pk}
        )


class ProjetNoteDeleteView(DeleteView):
    model = ProjetNote
    http_method_names = ["post"]

    def get_queryset(self):
        return ProjetNote.objects.filter(created_by=self.request.user)

    def get_success_url(self):
        messages.success(
            self.request,
            f'La note "{self.object.title}" a bien été supprimée.',
        )
        return reverse(
            "projet:get-projet-notes",
            kwargs={"projet_id": self.object.projet.pk},
        )


@method_decorator(htmx_only, name="get")
class ProjetNoteEditView(UpdateView):
    model = ProjetNote
    form_class = ProjetNoteForm
    template_name = "htmx/projet_note_update_form.html"

    def get_queryset(self):
        return ProjetNote.objects.filter(created_by=self.request.user)

    def get_success_url(self):
        return reverse("projet:note-card", kwargs={"pk": self.object.pk})


@method_decorator(htmx_only, name="dispatch")
class ProjetNoteCardView(DetailView):
    model = ProjetNote
    template_name = "includes/_projet_note_card.html"
    context_object_name = "note"
    http_method_names = ["get"]

    def get_queryset(self):
        return ProjetNote.objects.filter(
            projet__in=Projet.objects.for_user(self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["allow_update"] = True
        return context


class ProjetListViewFilters(ProjetFilters):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].queryset = Perimetre.objects.filter(
                Q(id=perimetre.id) | Q(id__in=perimetre.children().values("id"))
            )

        visible_projets = (
            Projet.objects.active().for_user(self.request.user).for_current_year()
        )

        self.filters["categorie_detr"].queryset = (
            CategorieDetr.objects.active()
            .filter(dossier__projet__in=visible_projets)
            .distinct()
            .order_by("rank")
        )

        self.filters["categorie_dsil"].queryset = (
            CategorieDsil.objects.active()
            .filter(dossier__projet__in=visible_projets)
            .distinct()
            .order_by("rank", "label")
        )

        visible_dossiers = visible_projets.values("dossier_ds")

        self.filters["epci"].extra["choices"] = lambda: tuple(
            (epci, epci.split(" - ", 1)[1] if " - " in epci else epci)
            for epci in visible_projets.values_list(
                "dossier_ds__porteur_de_projet_epci", flat=True
            )
            .distinct()
            .order_by("dossier_ds__porteur_de_projet_epci")
            if epci
        )

        self.filters["cofinancement"].queryset = (
            Cofinancement.objects.filter(dossier__in=visible_dossiers)
            .distinct()
            .order_by("id")
        )

        self.filters["zonage"].queryset = (
            ProjetZonage.objects.filter(dossier__in=visible_dossiers)
            .distinct()
            .order_by("id")
        )

        self.filters["contractualisation"].queryset = (
            ProjetContractualisation.objects.filter(dossier__in=visible_dossiers)
            .distinct()
            .order_by("id")
        )

    PROJET_LIST_ORDERING_MAP = {
        **ORDERING_MAP,
        "montant_retenu_total": "montant_retenu",
        "assiette_max": "assiette",
        "taux_max": "taux",
    }

    order = ProjetOrderingFilter(
        fields=PROJET_LIST_ORDERING_MAP,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    @property
    def qs(self):
        qs = super().qs
        qs = qs.annotate(
            montant_retenu_total=Sum("dotationprojet__programmation_projet__montant"),
            assiette_max=Max("dotationprojet__assiette"),
            taux_max=Max(
                Case(
                    When(
                        dotationprojet__assiette__gt=0,
                        dotationprojet__programmation_projet__montant__isnull=False,
                        then=F("dotationprojet__programmation_projet__montant")
                        * 100.0
                        / F("dotationprojet__assiette"),
                    ),
                    default=None,
                    output_field=DecimalField(),
                )
            ),
        )
        qs = qs.for_user(self.request.user)
        qs = qs.for_current_year()
        qs = qs.select_related(
            "address",
            "address__commune",
            "dossier_ds",
            "dossier_ds__ds_demandeur",
        ).prefetch_related(
            "dossier_ds__perimetre",
            "dossier_ds__demande_categorie_detr",
            "dossier_ds__demande_categorie_dsil",
            "dossier_ds__porteur_de_projet_arrondissement",
            "dotationprojet_set__programmation_projet",
            "dossier_ds__demande_cofinancements",
            "dossier_ds__projet_zonage",
            "dossier_ds__projet_contractualisation",
            Prefetch(
                "dossier_ds__ds_demarche",
            ),
        )
        return qs


class ProjetListView(FilterSkiplinksMixin, FilterView, ListView):
    model = Projet
    paginate_by = 25
    filterset_class = ProjetListViewFilters
    template_name = "gsl_projet/projet_list.html"

    def get_queryset(self):
        return Projet.objects.active().all()

    def get(self, request, *args, **kwargs):
        if "reset_filters" in request.GET:
            if request.path == reverse("gsl_projet:list"):
                return redirect(request.path)
            else:
                return redirect("/")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs_global = (
            self.filterset.qs
        )  # utile pour ne pas avoir la pagination de context["object_list"]
        context["title"] = "Projets"
        context["aggregates"] = qs_global.totals()
        context["enveloppes"] = (
            self.request.user.perimetre.enveloppe_set.for_current_year().all()
        )
        context["enveloppes_with_children"] = True
        context["columns"] = PROJET_TABLE_COLUMNS
        context["current_order"] = self.request.GET.get("order", "")
        context["sans_pieces_skip_keys"] = SANS_PIECES_SKIP_KEYS
        context["missing_annotations_count"] = (
            Projet.objects.active()
            .for_user(self.request.user)
            .with_missing_annotations()
            .count()
        )
        perimetre = getattr(self.request.user, "perimetre", None)
        if perimetre:
            context["territoire_choices"] = (perimetre, *perimetre.children())

        return context


class ProjetMissingAnnotationsListView(ListView):
    """Liste des projets acceptés sur DN avec des annotations DETR/DSIL incomplètes."""

    model = Projet
    paginate_by = 25
    template_name = "gsl_projet/projet_missing_annotations_list.html"
    context_object_name = "object_list"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Projets avec annotations manquantes"
        return context

    def get_queryset(self):
        return (
            Projet.objects.active()
            .for_user(self.request.user)
            .with_missing_annotations()
            .select_related(
                "dossier_ds",
                "dossier_ds__ds_demandeur",
            )
            .prefetch_related("dotationprojet_set", "dossier_ds__ds_demarche")
            .order_by("-dossier_ds__ds_date_depot")
        )
