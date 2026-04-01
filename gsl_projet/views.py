from django.contrib import messages
from django.db.models import Case, DecimalField, F, Max, Prefetch, Sum, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET
from django.views.generic import ListView, UpdateView
from django_filters.views import FilterView

from gsl_core.exceptions import Http404
from gsl_demarches_simplifiees.models import Demarche
from gsl_projet.forms import ProjetCommentForm
from gsl_projet.utils.django_filters_custom_widget import CustomSelectWidget
from gsl_projet.utils.projet_filters import (
    ORDERING_MAP,
    ProjetFilters,
    ProjetOrderingFilter,
)
from gsl_projet.utils.projet_page import PROJET_MENU
from gsl_projet.utils.utils import get_comment_cards

from .models import Projet
from .table_columns import PROJET_TABLE_COLUMNS, SANS_PIECES_SKIP_KEYS


def projet_visible_by_user(func):
    def wrapper(*args, **kwargs):
        user = args[0].user
        if user.is_staff:
            return func(*args, **kwargs)

        projet = get_object_or_404(Projet, id=kwargs["projet_id"])
        is_projet_visible_by_user = (
            Projet.objects.for_user(user).filter(id=projet.id).exists()
        )
        if not is_projet_visible_by_user:
            raise Http404(user_message="Projet non trouvé")

        return func(*args, **kwargs)

    return wrapper


def _get_projet_context_info(projet_id):
    projet = get_object_or_404(Projet, id=projet_id)
    title = projet.dossier_ds.projet_intitule
    context = {
        "title": title,
        "projet": projet,
        "dossier": projet.dossier_ds,
        "breadcrumb_dict": {
            "current": title,
        },
        "menu_dict": PROJET_MENU,
        "projet_notes": projet.notes.all(),
        "dotation_projets": projet.dotationprojet_set.all(),
        "comment_cards": get_comment_cards(projet),
    }
    return context


@projet_visible_by_user
@require_GET
def get_projet(request, projet_id):
    context = _get_projet_context_info(projet_id)
    return render(request, "gsl_projet/projet.html", context)


@projet_visible_by_user
@require_GET
def get_projet_notes(request, projet_id):
    context = _get_projet_context_info(projet_id)
    return render(request, "gsl_projet/projet/tab_notes.html", context)


class ProjetCommentUpdateView(UpdateView):
    model = Projet
    form_class = ProjetCommentForm
    pk_url_kwarg = "projet_id"
    http_method_names = ["post"]

    def get_queryset(self):
        return Projet.objects.for_user(self.request.user)

    def _get_redirect_url(self):
        next_url = self.request.POST.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts=self.request.get_host()
        ):
            return next_url
        return reverse("projet:get-projet-notes", kwargs={"projet_id": self.object.pk})

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, "Le commentaire a été enregistré avec succès.")
        return redirect(self._get_redirect_url())

    def form_invalid(self, form):
        return redirect(self._get_redirect_url())


class ProjetListViewFilters(ProjetFilters):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
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
            "demandeur",
            "dossier_ds",
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
                queryset=Demarche.objects.defer("raw_ds_data"),
            ),
        )
        return qs


class ProjetListView(FilterView, ListView):
    model = Projet
    paginate_by = 25
    filterset_class = ProjetListViewFilters
    template_name = "gsl_projet/projet_list.html"

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
        context["breadcrumb_dict"] = {}
        context["aggregates"] = qs_global.totals()
        context["enveloppes"] = (
            self.request.user.perimetre.enveloppe_set.for_current_year().all()
        )
        context["enveloppes_with_children"] = True
        context["columns"] = PROJET_TABLE_COLUMNS
        context["current_order"] = self.request.GET.get("order", "")
        context["sans_pieces_skip_keys"] = SANS_PIECES_SKIP_KEYS
        context["missing_annotations_count"] = (
            Projet.objects.for_user(self.request.user)
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
            Projet.objects.for_user(self.request.user)
            .with_missing_annotations()
            .select_related(
                "demandeur",
                "dossier_ds",
            )
            .prefetch_related("dotationprojet_set")
            .order_by("-dossier_ds__ds_date_depot")
        )
