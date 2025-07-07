from django.shortcuts import redirect
from django.views.generic.list import ListView

from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.constants import DOTATION_DETR


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
                "enveloppe",
                "enveloppe__perimetre",
            )
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


# class ProgrammationProjetListViewFilters(ProjetFilters):
# def __init__(self, *args, **kwargs):
#     super().__init__(*args, **kwargs)
#     self.slug = self.request.resolver_match.kwargs.get("slug")
#     simulation = Simulation.objects.select_related(
#         "enveloppe",
#         "enveloppe__perimetre",
#         "enveloppe__perimetre__region",
#         "enveloppe__perimetre__departement",
#         "enveloppe__perimetre__arrondissement",
#     ).get(slug=self.slug)
#     enveloppe = simulation.enveloppe
#     perimetre = enveloppe.perimetre

#     if perimetre:
#         self.filters["territoire"].extra["choices"] = tuple(
#             (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
#         )
#         self.filters["categorie_detr"].extra["choices"] = tuple(
#             (c.id, c.libelle)
#             for c in CategorieDetr.objects.current_for_departement(
#                 perimetre.departement
#             )
#         )

# filterset = (
#     "territoire",
#     "porteur",
#     "status",
#     "cout_total",
#     "montant_demande",
#     "montant_previsionnel",
#     "categorie_detr",
# )

# ordered_status = (
#     SimulationProjet.STATUS_PROCESSING,
#     SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
#     SimulationProjet.STATUS_REFUSED,
#     SimulationProjet.STATUS_ACCEPTED,
#     SimulationProjet.STATUS_DISMISSED,
# )

# status = MultipleChoiceFilter(
#     field_name="dotationprojet__simulationprojet__status",
#     choices=order_couples_tuple_by_first_value(
#         SimulationProjet.STATUS_CHOICES, ordered_status
#     ),
#     widget=CustomCheckboxSelectMultiple(),
#     method="filter_status",
# )

# def filter_status(self, queryset, name, value):
#     return queryset.filter(
#         # Cette ligne est utile pour qu'on ait un "ET", cad, on filtre les projets de la simulation en cours ET sur les statuts sélectionnés.
#         # Sans ça, on aurait dans l'ordre :
#         # - les projets dont IL EXISTE UN SIMULATION_PROJET (pas forcément celui de la simulation en question) qui a un des statuts sélectionnés
#         # - les simulation_projets de la simulation associés aux projets filtrés
#         **self._simulation_slug_filter_kwarg(),
#         dotationprojet__simulationprojet__status__in=value,
#     )

# montant_previsionnel_min = NumberFilter(
#     field_name="dotationprojet__simulationprojet__montant",
#     lookup_expr="gte",
#     widget=NumberInput(
#         attrs={"class": "fr-input", "min": "0"},
#     ),
#     method="filter_montant_previsionnel_min",
# )

# montant_previsionnel_max = NumberFilter(
#     field_name="dotationprojet__simulationprojet__montant",
#     lookup_expr="lte",
#     widget=NumberInput(
#         attrs={"class": "fr-input", "min": "0"},
#     ),
#     method="filter_montant_previsionnel_max",
# )

# def filter_montant_previsionnel_min(self, queryset, name, value):
#     return queryset.filter(
#         **self._simulation_slug_filter_kwarg(),
#         dotationprojet__simulationprojet__montant__gte=value,
#     )

# def filter_montant_previsionnel_max(self, queryset, name, value):
#     return queryset.filter(
#         **self._simulation_slug_filter_kwarg(),
#         dotationprojet__simulationprojet__montant__lte=value,
#     )

# def _simulation_slug_filter_kwarg(self):
#     return {"dotationprojet__simulationprojet__simulation__slug": self.slug}


# class ProgrammationDetrView(FilterView, ListView, FilterUtils):
#     model = ProgrammationProjet
#     paginate_by = 25

#     filterset_class = ProgrammationProjetListViewFilters
#     template_name = "gsl_programmation/programmation_detr_list.html"
#     # STATE_MAPPINGS = {key: value for key, value in SimulationProjet.STATUS_CHOICES}

#     def get(self, request, *args, **kwargs):
#         if "reset_filters" in request.GET:
#             return redirect(request.path)

#         # self.object = self.get_object()
#         self.perimetre = self.request.user.perimetre
#         enveloppe_qs = (
#             Enveloppe.objects.select_related(
#                 "perimetre",
#                 "perimetre__region",
#                 "perimetre__departement",
#                 "perimetre__arrondissement",
#             )
#             .filter(dotation=DOTATION_DETR)
#             .order_by("-annee")
#         )
#         if self.perimetre:
#             enveloppe_qs = enveloppe_qs.filter(perimetre=self.perimetre)
#         self.enveloppe = enveloppe_qs.first()
#         return super().get(request, *args, **kwargs)

#     # def get_object(self, queryset=None):
#     #     # surcharge pour éviter les requêtes multiples
#     #     if hasattr(self, "object") and self.object:
#     #         return self.object
#     #     return super().get_object(queryset)

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         # qs_global = (
#         #     self.filterset.qs
#         # )  # utile pour ne pas avoir la pagination de context["object_list"]
#         context["title"] = "Projets"
#         context["breadcrumb_dict"] = {}
#         # context["total_cost"] = ProjetService.get_total_cost(qs_global)
#         # context["total_amount_asked"] = ProjetService.get_total_amount_asked(qs_global)
#         # context["total_amount_granted"] = ProjetService.get_total_amount_granted(
#         #     qs_global
#         # )
#         self.enrich_context_with_filter_utils(context, self.STATE_MAPPINGS)

#         return context
