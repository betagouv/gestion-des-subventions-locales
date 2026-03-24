from django.forms import NumberInput
from django_filters import FilterSet, MultipleChoiceFilter, NumberFilter

from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_projet.models import Projet
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
)
from gsl_projet.utils.projet_filters import (
    ORDERING_LABELS,
    ORDERING_MAP,
    ProjetOrderingFilter,
    filter_territoire,
)
from gsl_projet.utils.utils import order_couples_tuple_by_first_value
from gsl_simulation.models import Simulation, SimulationProjet


class SimulationProjetFilters(FilterSet):
    def __init__(self, *args, slug=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.slug = slug or self.request.resolver_match.kwargs.get("slug")
        simulation = Simulation.objects.select_related(
            "enveloppe",
            "enveloppe__perimetre",
            "enveloppe__perimetre__region",
            "enveloppe__perimetre__departement",
            "enveloppe__perimetre__arrondissement",
        ).get(slug=self.slug)
        enveloppe = simulation.enveloppe
        perimetre = enveloppe.perimetre

        if perimetre:
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )

    filterset = (
        "territoire",
        "porteur",
        "status",
        "cout_total",
        "montant_demande",
        "montant_previsionnel",
    )

    SIMULATION_ORDERING_MAP = {
        **ORDERING_MAP,
        "dotationprojet__simulationprojet__montant": "montant_previsionnel",
    }

    SIMULATION_ORDERING_LABELS = {
        **ORDERING_LABELS,
        "dotationprojet__simulationprojet__montant": "Montant prévisionnel",
    }

    order = ProjetOrderingFilter(
        fields=SIMULATION_ORDERING_MAP,
        field_labels=SIMULATION_ORDERING_LABELS,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    porteur = MultipleChoiceFilter(
        field_name="dossier_ds__porteur_de_projet_nature__type",
        choices=NaturePorteurProjet.TYPE_CHOICES,
        widget=CustomCheckboxSelectMultiple(),
    )

    cout_min = NumberFilter(
        field_name="dossier_ds__finance_cout_total",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    cout_max = NumberFilter(
        field_name="dossier_ds__finance_cout_total",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
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

    territoire = MultipleChoiceFilter(
        method="filter_territoire",
        choices=[],
        widget=CustomCheckboxSelectMultiple(),
    )

    ordered_status = (
        SimulationProjet.STATUS_PROCESSING,
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_DISMISSED,
    )

    status = MultipleChoiceFilter(
        field_name="dotationprojet__simulationprojet__status",
        choices=order_couples_tuple_by_first_value(
            SimulationProjet.STATUS_CHOICES, ordered_status
        ),
        widget=CustomCheckboxSelectMultiple(),
        method="filter_status",
    )

    montant_previsionnel_min = NumberFilter(
        field_name="dotationprojet__simulationprojet__montant",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
        method="filter_montant_previsionnel_min",
    )

    montant_previsionnel_max = NumberFilter(
        field_name="dotationprojet__simulationprojet__montant",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
        method="filter_montant_previsionnel_max",
    )

    filter_territoire = staticmethod(filter_territoire)

    def filter_status(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            dotationprojet__simulationprojet__status__in=value,
        )

    def filter_montant_previsionnel_min(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            dotationprojet__simulationprojet__montant__gte=value,
        )

    def filter_montant_previsionnel_max(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            dotationprojet__simulationprojet__montant__lte=value,
        )

    def _simulation_slug_filter_kwarg(self):
        return {"dotationprojet__simulationprojet__simulation__slug": self.slug}

    class Meta:
        model = Projet
        fields = []

    @property
    def qs(self):
        self.queryset = Projet.objects.all()
        return super().qs
