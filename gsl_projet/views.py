from functools import cached_property

from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views.generic import ListView
from django_filters.views import FilterView

from gsl_projet.constants import PROJET_STATUS_CHOICES
from gsl_projet.services.projet_services import ProjetService
from gsl_projet.utils.django_filters_custom_widget import CustomSelectWidget
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.utils.projet_filters import BaseProjetFilters, ProjetOrderingFilter
from gsl_projet.utils.projet_page import PROJET_MENU

from .models import CategorieDetr, Projet


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
            raise Http404("No %s matches the given query." % Projet._meta.object_name)

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
    }
    return context


@projet_visible_by_user
@require_GET
def get_projet(request, projet_id):
    context = _get_projet_context_info(projet_id)
    return render(request, "gsl_projet/projet.html", context)


PROJET_TABS = {"annotations", "historique"}


@projet_visible_by_user
@require_GET
def get_projet_tab(request, projet_id, tab):
    if tab not in PROJET_TABS:
        raise Http404
    context = _get_projet_context_info(projet_id)
    return render(request, f"gsl_projet/projet/tab_{tab}.html", context)


class ProjetListViewFilters(BaseProjetFilters):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )
            if perimetre.departement:
                self.filters["categorie_detr"].extra["choices"] = tuple(
                    (c.id, c.libelle)
                    for c in CategorieDetr.objects.current_for_departement(
                        perimetre.departement
                    )
                )

    ORDERING_MAP = {
        **BaseProjetFilters.ORDERING_MAP,
        "montant_retenu_total": "montant_retenu",
    }

    ORDERING_LABELS = {
        **BaseProjetFilters.ORDERING_LABELS,
        "montant_retenu_total": "Montant retenu",
    }

    order = ProjetOrderingFilter(
        fields=ORDERING_MAP,
        field_labels=ORDERING_LABELS,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    filterset = (
        "territoire",
        "porteur",
        "dotation",
        "status",
        "cout_total",
        "montant_demande",
        "montant_retenu",
        "categorie_detr",
    )

    @property
    def qs(self):
        qs = super().qs
        qs = qs.annotate(
            montant_retenu_total=Sum("dotationprojet__programmation_projet__montant")
        )
        qs = qs.for_user(self.request.user)
        qs = qs.for_current_year()
        qs = qs.select_related(
            "address",
            "address__commune",
            "perimetre",
            "demandeur",
        ).prefetch_related(
            "dossier_ds__demande_eligibilite_detr",
            "dossier_ds__demande_eligibilite_dsil",
            "dotationprojet_set__detr_categories",
            "dotationprojet_set__programmation_projet",
        )
        return qs


class ProjetListView(FilterView, ListView, FilterUtils):
    model = Projet
    paginate_by = 25
    filterset_class = ProjetListViewFilters
    template_name = "gsl_projet/projet_list.html"
    STATE_MAPPINGS = {key: value for key, value in PROJET_STATUS_CHOICES}

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
        context["total_cost"] = ProjetService.get_total_cost(qs_global)
        context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs_global)
        context["total_amount_granted"] = ProjetService.get_total_amount_granted(
            qs_global
        )
        context["enveloppes"] = self.request.user.perimetre.enveloppe_set.filter(
            annee=self.request.user.perimetre.enveloppe_set.order_by("-annee")
            .values_list("annee", flat=True)
            .first()
        ).all()
        context["enveloppes_with_children"] = True
        self.enrich_context_with_filter_utils(context, self.STATE_MAPPINGS)

        return context

    def _get_perimetre(self):
        if hasattr(self.request, "user") and self.request.user.perimetre:
            return self.request.user.perimetre

    def _get_territoire_choices(self):
        perimetre = self._get_perimetre()
        if not perimetre:
            return ()

        return (perimetre, *perimetre.children())

    @cached_property
    def categorie_detr_choices(self):
        perimetre = self._get_perimetre()
        if not perimetre:
            return ()

        if not perimetre.departement:
            return ()

        return CategorieDetr.objects.current_for_departement(perimetre.departement)
