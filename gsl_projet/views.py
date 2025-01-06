import datetime

from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views.generic import ListView

from gsl_demarches_simplifiees.models import NaturePorteurProjet

from .models import Projet


@require_GET
def get_projet(request, projet_id):
    projet = get_object_or_404(Projet, id=projet_id)
    context = {
        "title": f"Projet {projet}",
        "projet": projet,
        "dossier": projet.dossier_ds,
        "breadcrumb_dict": {
            "links": [{"url": reverse("projet:list"), "title": "Liste des projets"}],
            "current": f"Projet {projet}",
        },
        "menu_dict": {
            "title": "Menu",
            "items": (
                {
                    "label": "1 – Porteur de projet",
                    "link": "#porteur_de_projet",
                },
                {
                    "label": "2 – Présentation de l’opération",
                    "items": (
                        {
                            "label": "Projet",
                            "link": "#presentation_projet",
                        },
                        {
                            "label": "Dates",
                            "link": "#presentation_dates",
                        },
                        {
                            "label": "Détails du projet",
                            "link": "#presentation_details_proj",
                        },
                        {
                            "label": "Transition écologique",
                            "link": "#presentation_transition_eco",
                        },
                    ),
                },
                {
                    "label": "3 – Plan de financement prévisionnel",
                    "items": (
                        {
                            "label": "Coûts de financement",
                            "link": "#couts_financement",
                        },
                        {
                            "label": "Détails  du financement",
                            "link": "#detail_financement",
                        },
                        {
                            "label": "Dispositifs de financement sollicités",
                            "link": "#dispositifs_sollicites",
                        },
                        # {
                        #    "label": "Autres opérations en demande de subvention DETR/DSIL 2024",
                        #    "link": "(OR) the link (fragment) of the menu item",
                        # },
                    ),
                },
            ),
        },
    }
    return render(request, "gsl_projet/projet.html", context)


class ProjetListView(ListView):
    model = Projet
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Projets 2025"
        return context

    def get_ordering(self):
        ordering_map = {
            "date_desc": "-dossier_ds__ds_date_depot",
            "date_asc": "dossier_ds__ds_date_depot",
            "cout_desc": "-dossier_ds__finance_cout_total",
            "cout_asc": "dossier_ds__finance_cout_total",
            "commune_desc": "-address__commune__name",
            "commune_asc": "address__commune__name",
        }

        tri = self.request.GET.get("tri")
        return ordering_map.get(tri, None)

    def get_queryset(self):
        qs = Projet.objects.for_user(self.request.user).filter(
            dossier_ds__ds_date_depot__gte=datetime.date(2024, 9, 1)
        )

        # Filtre par dispositif
        dispositif = self.request.GET.get("dispositif")
        if dispositif:
            qs = qs.filter(dossier_ds__demande_dispositif_sollicite=dispositif)

        porteur = self.request.GET.get("porteur")
        if porteur == "EPCI":
            qs = qs.filter(
                dossier_ds__porteur_de_projet_nature__label__in=NaturePorteurProjet.EPCI_NATURES
            )
        elif porteur == "Communes":
            qs = qs.filter(
                dossier_ds__porteur_de_projet_nature__label__in=NaturePorteurProjet.COMMUNE_NATURES
            )

        # Tri
        ordering = self.get_ordering()
        if ordering:
            qs = qs.order_by(ordering)

        return qs
