from functools import cached_property

from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django_filters.views import FilterView

from gsl_core.models import Perimetre
from gsl_programmation.forms import SubEnveloppeForm
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_programmation.utils.programmation_projet_filters import (
    ProgrammationProjetFilters,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import CategorieDetr
from gsl_projet.utils.filter_utils import FilterUtils
from gsl_projet.utils.projet_page import PROJET_MENU


class ProgrammationProjetDetailView(DetailView):
    model = ProgrammationProjet

    ALLOWED_TABS = {"annotations", "historique"}

    def get_template_names(self):
        if "tab" in self.kwargs:
            tab = self.kwargs["tab"]
            if tab not in self.ALLOWED_TABS:
                raise Http404
            return [f"gsl_programmation/tab_programmation_projet/tab_{tab}.html"]
        return ["gsl_programmation/programmation_projet_detail.html"]

    def get_object(self, queryset=None):
        self.programmation_projet = (
            ProgrammationProjet.objects.select_related(
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
                "dotation_projet__projet__perimetre",
                "dotation_projet__projet__demandeur",
                "enveloppe",
                "enveloppe__perimetre",
            )
            .prefetch_related("dotation_projet__detr_categories")
            .get(pk=self.kwargs.get("programmation_projet_id"))
        )
        return self.programmation_projet

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab = self.kwargs.get("tab", "projet")
        title = self.programmation_projet.projet.dossier_ds.projet_intitule
        context = {
            "title": title,
            "programmation_projet": self.programmation_projet,
            "projet": self.programmation_projet.projet,
            "dossier": self.programmation_projet.projet.dossier_ds,
            "enveloppe": self.programmation_projet.enveloppe,
            "breadcrumb_dict": {
                "links": [
                    {
                        "url": reverse("gsl_programmation:programmation-projet-list"),
                        "title": "Programmation en cours",
                    },
                ],
                "current": title,
            },
            "menu_dict": PROJET_MENU,
            "current_tab": tab,
        }
        if tab == "annotations":
            context["projet_notes"] = self.programmation_projet.projet.notes.all()

        return context


class ProgrammationProjetListView(FilterView, ListView, FilterUtils):
    model = ProgrammationProjet
    filterset_class = ProgrammationProjetFilters
    template_name = "gsl_programmation/programmation_projet_list.html"
    context_object_name = "programmation_projets"
    paginate_by = 25
    ordering = ["-created_at"]
    STATE_MAPPINGS = {key: value for key, value in ProgrammationProjet.STATUS_CHOICES}

    def get(self, request, *args, **kwargs):
        self.perimetre: Perimetre = self.request.user.perimetre
        self.dotation = kwargs.get("dotation")
        if self.dotation is None:
            return redirect(
                "gsl_programmation:programmation-projet-list-dotation",
                dotation=DOTATION_DETR,
            )
        if self.dotation not in (DOTATION_DETR, DOTATION_DSIL):
            raise Http404("Dotation non reconnue.")

        if (
            self.dotation == DOTATION_DETR
            and self.perimetre.type == Perimetre.TYPE_REGION
        ):
            return redirect(
                "gsl_programmation:programmation-projet-list-dotation", dotation="DSIL"
            )

        if "reset_filters" in request.GET:
            if request.path.startswith("/programmation/liste/"):
                return redirect(request.path)
            else:
                return redirect("/")

        enveloppe_qs = (
            Enveloppe.objects.select_related(
                "perimetre",
                "perimetre__region",
                "perimetre__departement",
                "perimetre__arrondissement",
            )
            .filter(dotation=self.dotation)
            .order_by("-annee")
        )

        self.enveloppe = self._get_enveloppe_from_user_perimetre(
            self.perimetre, enveloppe_qs
        )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        title = "Programmation en cours"
        if self.enveloppe:
            title = f"Programmation {self.enveloppe.dotation} {self.enveloppe.annee}"
        context.update(
            {
                "enveloppe": self.enveloppe,
                "dotation": self.enveloppe.dotation,
                "title": title,
                "to_notify_projets_count": self.object_list.to_notify().count(),
                "activate_all_projets_selection": self.object_list.count()
                > ProgrammationProjetListView.paginate_by,
                "breadcrumb_dict": {
                    "current": "Programmation en cours",
                },
                "current_tab": self.dotation,
                "is_detr_disabled": self.perimetre.type == Perimetre.TYPE_REGION,
            }
        )

        ignore_categories_detr = bool(self.dotation == DOTATION_DSIL)
        self.enrich_context_with_filter_utils(
            context, self.STATE_MAPPINGS, ignore_categories_detr=ignore_categories_detr
        )

        return context

    def _get_enveloppe_from_user_perimetre(self, perimetre, enveloppe_qs):
        """
        Returns the enveloppe corresponding to the user's perimetre.
        If no enveloppe is found, it returns None.
        """
        if not perimetre:
            return enveloppe_qs.first()

        perimetre_enveloppe_qs = enveloppe_qs.filter(perimetre=perimetre)
        enveloppe = perimetre_enveloppe_qs.first()
        if enveloppe is not None:
            return enveloppe

        perimetre_enveloppe_qs = enveloppe_qs.filter(
            perimetre__departement=perimetre.departement
        )
        enveloppe = perimetre_enveloppe_qs.first()
        if enveloppe is not None:
            return enveloppe

        perimetre_enveloppe_qs = enveloppe_qs.filter(perimetre__region=perimetre.region)
        enveloppe = perimetre_enveloppe_qs.first()
        if enveloppe is not None:
            return enveloppe

        raise Http404("Aucune enveloppe trouvée pour le périmètre de l'utilisateur.")

    # Filter functions

    def _get_perimetre(self):
        return self.perimetre

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


class EnveloppeCreateView(CreateView):
    model = Enveloppe
    form_class = SubEnveloppeForm
    success_url = reverse_lazy("gsl_projet:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user_perimetre"] = self.request.user.perimetre
        return kwargs

    def get_perimetres_qs(self):
        return Perimetre.objects.filter(
            pk__in=(
                p.id
                for p in (
                    self.request.user.perimetre,
                    *self.request.user.perimetre.children(),
                )
            ),
        )
