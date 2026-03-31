from django.db import models
from django.db.models import Case, DecimalField, F, Subquery, When
from django_filters import (
    DateFromToRangeFilter,
    FilterSet,
    MultipleChoiceFilter,
    RangeFilter,
)

from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_projet.models import Projet
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
    DsfrDateRangeWidget,
    DsfrRangeWidget,
)
from gsl_projet.utils.projet_filters import (
    ORDERING_MAP,
    ProjetOrderingFilter,
    filter_territoire,
)
from gsl_projet.utils.utils import order_couples_tuple_by_first_value
from gsl_simulation.models import SimulationProjet


class SimulationProjetFilters(FilterSet):
    def __init__(self, *args, slug=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.slug = slug or self.request.resolver_match.kwargs.get("slug")

        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )

    SIMULATION_ORDERING_MAP = {
        **ORDERING_MAP,
        "simu_montant": "montant_previsionnel",
        "simu_assiette": "assiette",
        "simu_taux": "taux",
    }

    porteur = MultipleChoiceFilter(
        label="Demandeur",
        field_name="dossier_ds__porteur_de_projet_nature__type",
        choices=NaturePorteurProjet.TYPE_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    ordered_status = (
        SimulationProjet.STATUS_PROCESSING,
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_DISMISSED,
    )

    status = MultipleChoiceFilter(
        label="Statut",
        field_name="dotationprojet__simulationprojet__status",
        choices=order_couples_tuple_by_first_value(
            SimulationProjet.STATUS_CHOICES, ordered_status
        ),
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
        method="filter_status",
    )

    cout = RangeFilter(
        label="Coût total",
        field_name="dossier_ds__finance_cout_total",
        widget=DsfrRangeWidget(icon="fr-icon-coin-fill"),
    )

    montant_demande = RangeFilter(
        label="Montant demandé",
        field_name="dossier_ds__demande_montant",
        widget=DsfrRangeWidget(
            icon="fr-icon-money-euro-circle-fill",
            display_template="includes/_filter_montant_demande.html",
        ),
    )

    montant_previsionnel = RangeFilter(
        label="Montant prévisionnel accordé",
        field_name="dotationprojet__simulationprojet__montant",
        widget=DsfrRangeWidget(icon="fr-icon-money-euro-box-fill"),
        method="filter_montant_previsionnel",
    )

    date_depot = DateFromToRangeFilter(
        label="Date de dépôt",
        field_name="dossier_ds__ds_date_depot__date",
        widget=DsfrDateRangeWidget(icon="fr-icon-calendar-line"),
    )

    date_debut = DateFromToRangeFilter(
        label="Date de commencement",
        field_name="dossier_ds__date_debut",
        widget=DsfrDateRangeWidget(icon="fr-icon-calendar-line"),
    )

    date_achevement = DateFromToRangeFilter(
        label="Date d'achèvement",
        field_name="dossier_ds__date_achevement",
        widget=DsfrDateRangeWidget(icon="fr-icon-calendar-line"),
    )

    territoire = MultipleChoiceFilter(
        method="filter_territoire",
        choices=[],
        widget=CustomCheckboxSelectMultiple(
            display_template="includes/_filter_territoire.html"
        ),
    )

    order = ProjetOrderingFilter(
        fields=SIMULATION_ORDERING_MAP,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    filter_territoire = staticmethod(filter_territoire)

    def filter_status(self, queryset, name, value):
        return queryset.filter(
            **self._simulation_slug_filter_kwarg(),
            dotationprojet__simulationprojet__status__in=value,
        )

    def filter_montant_previsionnel(self, queryset, _name, value):
        kwargs = self._simulation_slug_filter_kwarg()
        if value.start is not None:
            queryset = queryset.filter(
                **kwargs, dotationprojet__simulationprojet__montant__gte=value.start
            )
        if value.stop is not None:
            queryset = queryset.filter(
                **kwargs, dotationprojet__simulationprojet__montant__lte=value.stop
            )
        return queryset

    def _simulation_slug_filter_kwarg(self):
        return {"dotationprojet__simulationprojet__simulation__slug": self.slug}

    class Meta:
        model = Projet
        fields = (
            "territoire",
            "porteur",
            "status",
            "cout",
            "montant_demande",
            "montant_previsionnel",
            "date_depot",
            "date_debut",
            "date_achevement",
        )

    @property
    def qs(self):
        from gsl_projet.models import DotationProjet

        slug_filter = {"simulationprojet__simulation__slug": self.slug}
        simu_dp_qs = DotationProjet.objects.filter(
            projet=models.OuterRef("pk"), **slug_filter
        )

        qs = super().qs.annotate(
            simu_montant=Subquery(simu_dp_qs.values("simulationprojet__montant")[:1]),
            simu_assiette=Subquery(simu_dp_qs.values("assiette")[:1]),
        )
        return qs.annotate(
            simu_taux=Case(
                When(
                    simu_assiette__gt=0,
                    then=F("simu_montant") * 100.0 / F("simu_assiette"),
                ),
                When(
                    dossier_ds__finance_cout_total__gt=0,
                    then=F("simu_montant")
                    * 100.0
                    / F("dossier_ds__finance_cout_total"),
                ),
                default=None,
                output_field=DecimalField(),
            ),
        )
