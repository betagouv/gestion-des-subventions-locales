from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.utils.projet_page import PROJET_MENU


# TODO adapt CorrectUserPerimeterRequiredMixin !
class ProgrammationProjetDetailView(DetailView):
    model = ProgrammationProjet

    ALLOWED_TABS = {"annotations", "historique", "notifications"}

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
        title = f"Programmation - {self.programmation_projet.projet.dossier_ds.projet_intitule}"
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


class ProgrammationProjetListView(ListView):
    model = ProgrammationProjet
    template_name = "gsl_programmation/programmation_projet_list.html"
    context_object_name = "programmation_projets"
    paginate_by = 25
    ordering = ["-created_at"]

    def get(self, request, *args, **kwargs):
        if "reset_filters" in request.GET:
            return redirect(request.path)

        self.perimetre = self.request.user.perimetre
        enveloppe_qs = (
            Enveloppe.objects.select_related(
                "perimetre",
                "perimetre__region",
                "perimetre__departement",
                "perimetre__arrondissement",
            )
            .filter(dotation=DOTATION_DETR)
            .order_by("-annee")
        )
        if self.perimetre:
            enveloppe_qs = enveloppe_qs.filter(perimetre=self.perimetre)
        self.enveloppe = enveloppe_qs.first()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return (
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
            .filter(enveloppe=self.enveloppe)
            .order_by(self.ordering[0])
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        title = "Projets programmés"
        if self.enveloppe:
            title = f"Programmation {self.enveloppe.dotation} {self.enveloppe.annee}"
        context.update(
            {
                "enveloppe": self.enveloppe,
                "title": title,
                "breadcrumb_dict": {
                    "current": "Programmation en cours",
                },
            }
        )

        return context
