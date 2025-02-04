from django.db.models import Q
from django.forms import NumberInput, Select
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.views.generic import ListView
from django_filters import ChoiceFilter, FilterSet, NumberFilter
from django_filters.views import FilterView

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.services import ProjetService

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


class ProjetFilters(FilterSet):
    dotation = ChoiceFilter(
        field_name="dossier_ds__demande_dispositif_sollicite",
        choices=Dossier.DEMANDE_DISPOSITIF_SOLLICITE_VALUES,
        widget=Select(
            attrs={
                "class": "fr-select",
                "onchange": "this.form.submit()",
                "placeholder": "Toutes les dotations",
            }
        ),
    )

    porteur = ChoiceFilter(
        field_name="dossier_ds__porteur_de_projet_nature__label__in",
        choices=(
            ("EPCI", "EPCI"),
            ("Communes", "Communes"),
        ),
        method="filter_porteur",
        widget=Select(
            attrs={
                "class": "fr-select",
                "onchange": "this.form.submit()",
                "placeholder": "Tous les porteurs",
            },
        ),
    )

    def filter_porteur(self, queryset, _name, value):
        return queryset.filter(
            dossier_ds__porteur_de_projet_nature__label__in=ProjetService.PORTEUR_MAPPINGS.get(
                value
            )
        )

    cout_min = NumberFilter(
        method="filter_cout_min",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    def filter_cout_min(self, queryset, _name, value):
        return queryset.filter(
            Q(assiette__isnull=False, assiette__gte=value)
            | Q(assiette__isnull=True, dossier_ds__finance_cout_total__gte=value)
        )

    cout_max = NumberFilter(
        method="filter_cout_max",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    def filter_cout_max(self, queryset, _name, value):
        return queryset.filter(
            Q(assiette__isnull=False, assiette__lte=value)
            | Q(assiette__isnull=True, dossier_ds__finance_cout_total__lte=value)
        )

    montant_demande_max = NumberFilter(
        field_name="dossier_ds__demande_montant",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_demande_min = NumberFilter(
        field_name="dossier_ds__demande_montant",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_retenu_min = NumberFilter(
        field_name="dossier_ds__annotations_montant_accorde",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_retenu_max = NumberFilter(
        field_name="dossier_ds__annotations_montant_accorde",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    class Meta:
        model = Projet
        fields = [
            "dotation",
            "porteur",
            "cout_min",
            "cout_max",
            "montant_demande_min",
            "montant_demande_max",
            "montant_retenu_min",
            "montant_retenu_max",
        ]

    @property
    def qs(self):
        qs = super().qs
        qs = qs.for_user(self.request.user)
        qs = qs.for_current_year()
        qs = ProjetService.add_ordering_to_projets_qs(qs, self.request.GET.get("tri"))
        return qs


class ProjetListView(FilterView, ListView):
    model = Projet
    paginate_by = 25
    filterset_class = ProjetFilters
    template_name = "gsl_projet/projet_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context["title"] = "Projets 2025"
        context["porteur_mappings"] = ProjetService.PORTEUR_MAPPINGS
        context["breadcrumb_dict"] = {"current": "Liste des projets"}
        context["total_cost"] = ProjetService.get_total_cost(qs)
        context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs)
        context["total_amount_granted"] = 0  # TODO
        context["is_cout_total_active"] = self._get_is_one_field_active(
            ["cout_min", "cout_max"]
        )
        context["is_montant_demande_active"] = self._get_is_one_field_active(
            ["montant_demande_min", "montant_demande_max"]
        )
        context["is_montant_retenu_active"] = self._get_is_one_field_active(
            ["montant_retenu_min", "montant_retenu_max"]
        )

        return context

    def _get_is_one_field_active(self, field_names):
        for field_name in field_names:
            if self.request.GET.get(field_name) not in (None, ""):
                return True
        return False
