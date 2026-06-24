import json

from django.contrib import messages
from django.db.models import Case, DecimalField, F, Max, Prefetch, Q, Sum, When
from django.shortcuts import get_object_or_404, redirect
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

from gsl_core.decorators import htmx_only
from gsl_core.models import Perimetre
from gsl_core.view_mixins import SafeRedirectMixin
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    CategorieDsil,
    Cofinancement,
    ProjetContractualisation,
    ProjetZonage,
)
from gsl_projet.forms import (
    DotationProjetForm,
    ProjetCommentForm,
    ProjetForm,
    ProjetNoteForm,
)
from gsl_projet.models import DotationProjet, ProjetNote
from gsl_projet.utils.django_filters_custom_widget import CustomSelectWidget
from gsl_projet.utils.projet_filters import (
    ORDERING_MAP,
    ProjetFilters,
    ProjetOrderingFilter,
)
from gsl_projet.utils.projet_page import PROJET_MENU, get_projet_go_back_context
from gsl_projet.utils.utils import get_comment_cards

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
        projet = self.object
        context = super().get_context_data(**kwargs)
        projet_form = ProjetForm(instance=projet)
        dotation_field = projet_form.fields.get("dotations")
        context.update(
            {
                "title": projet.dossier_ds.projet_intitule,
                "dossier": projet.dossier_ds,
                "menu_dict": PROJET_MENU,
                "projet_notes": projet.notes.all(),
                "dotation_projets": projet.dotationprojet_set.order_by(
                    "dotation"
                ).all(),
                "comment_cards": get_comment_cards(projet),
                "projet_form": projet_form,
                "initial_dotations": (
                    json.dumps(dotation_field.initial) if dotation_field else "[]"
                ),
                **get_projet_go_back_context(self.request),
            }
        )
        detr_dotation = projet.dotation_detr
        if detr_dotation:
            context["dotation_projet_form"] = DotationProjetForm(instance=detr_dotation)
            context["dotation_projet"] = detr_dotation
        context["projet_note_form"] = ProjetNoteForm()
        return context


class ProjetHistoriqueView(BaseProjetDetailView):
    template_name = "gsl_projet/projet/tab_historique.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["actions"] = self.object.actions.select_related("actor").order_by(
            "-created_at"
        )
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


class ProjetUpdateView(UpdateView):
    model = Projet
    form_class = ProjetForm
    pk_url_kwarg = "projet_id"
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
        return _redirect_to_referer_or_projet(self.request, self.object)


class DotationProjetUpdateView(UpdateView):
    model = DotationProjet
    form_class = DotationProjetForm
    http_method_names = ["post"]

    def get_queryset(self):
        return DotationProjet.objects.filter(
            projet__in=Projet.objects.active().for_user(self.request.user)
        )

    def form_valid(self, form):
        form.save()
        messages.success(
            self.request,
            "Les modifications ont été enregistrées avec succès.",
        )
        return _redirect_to_referer_or_projet(self.request, self.object.projet)

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Une erreur s'est produite lors de la soumission du formulaire.",
        )
        return _redirect_to_referer_or_projet(self.request, self.object.projet)


class ProjetNoteCreateView(CreateView):
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
        messages.error(
            self.request,
            "Une erreur s'est produite lors de la soumission du formulaire.",
        )
        return redirect("projet:get-projet-notes", projet_id=self.kwargs["projet_id"])

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


class ProjetListView(FilterView, ListView):
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
