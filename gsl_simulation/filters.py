from django.db import models
from django.db.models import Case, DecimalField, F, Q, Subquery, When
from django_filters import (
    CharFilter,
    DateFromToRangeFilter,
    FilterSet,
    ModelMultipleChoiceFilter,
    MultipleChoiceFilter,
    RangeFilter,
)

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    CategorieDsil,
    Cofinancement,
    NaturePorteurProjet,
    ProjetContractualisation,
    ProjetZonage,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import Projet
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
    DsfrDateRangeWidget,
    DsfrRangeWidget,
)
from gsl_projet.utils.projet_filters import (
    DOTATION_SOLLICITEE_CHOICES,
    ORDERING_MAP,
    OUI_NON_CHOICES,
    LabelFromInstanceFilter,
    ProjetOrderingFilter,
    filter_boolean,
    filter_dossier_complet,
    filter_dotation_sollicitee,
    filter_territoire,
    make_filter_search,
)
from gsl_projet.utils.utils import order_couples_tuple_by_first_value
from gsl_simulation.models import SimulationProjet


class SimulationProjetFilters(FilterSet):
    def __init__(self, *args, slug=None, dotation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.slug = slug or self.request.resolver_match.kwargs.get("slug")

        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].queryset = Perimetre.objects.filter(
                Q(id=perimetre.id) | Q(id__in=perimetre.children().values("id"))
            )

        if dotation == DOTATION_DETR:
            self.filters["categorie_detr"].queryset = (
                CategorieDetr.objects.active()
                .filter(dossier__projet__in=self.queryset)
                .distinct()
                .order_by("rank")
            )
        else:
            del self.filters["categorie_detr"]

        if dotation == DOTATION_DSIL:
            self.filters["categorie_dsil"].queryset = (
                CategorieDsil.objects.active()
                .filter(dossier__projet__in=self.queryset)
                .distinct()
                .order_by("rank", "label")
            )
        else:
            del self.filters["categorie_dsil"]

        visible_dossiers = self.queryset.values("dossier_ds")

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

        projets_queryset = self.queryset

        self.filters["epci"].extra["choices"] = lambda: tuple(
            (epci, epci.split(" - ", 1)[1] if " - " in epci else epci)
            for epci in projets_queryset.values_list(
                "dossier_ds__porteur_de_projet_epci", flat=True
            )
            .distinct()
            .order_by("dossier_ds__porteur_de_projet_epci")
            if epci
        )

    SIMULATION_ORDERING_MAP = {
        **ORDERING_MAP,
        "simu_montant": "montant_previsionnel",
        "simu_assiette": "assiette",
        "simu_taux": "taux",
    }

    search = CharFilter(
        label="Recherche",
        method="filter_search",
    )

    categorie_detr = LabelFromInstanceFilter(
        label="Catégorie DETR",
        field_name="dossier_ds__demande_categorie_detr",
        queryset=CategorieDetr.objects.none(),
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
        label_attr="complete_label",
    )

    categorie_dsil = ModelMultipleChoiceFilter(
        label="Catégorie DSIL",
        field_name="dossier_ds__demande_categorie_dsil",
        queryset=CategorieDsil.objects.none(),
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

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

    territoire = LabelFromInstanceFilter(
        method="filter_territoire",
        queryset=Perimetre.objects.none(),
        widget=CustomCheckboxSelectMultiple(
            display_template="includes/_filter_territoire.html"
        ),
        label_attr="entity_name",
    )

    budget_vert_demandeur = MultipleChoiceFilter(
        label="Budget vert (demandeur)",
        field_name="dossier_ds__environnement_transition_eco",
        choices=OUI_NON_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
        method="filter_boolean",
    )

    budget_vert_instructeur = MultipleChoiceFilter(
        label="Budget vert (instructeur)",
        field_name="is_budget_vert",
        choices=OUI_NON_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
        method="filter_boolean",
    )

    dotation_sollicitee = MultipleChoiceFilter(
        label="Dotation sollicitée",
        field_name="dossier_ds__demande_dispositif_sollicite",
        choices=DOTATION_SOLLICITEE_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
        method="filter_dotation_sollicitee",
    )

    dossier_complet = MultipleChoiceFilter(
        label="Dossier complet",
        field_name="dossier_ds__ds_state",
        choices=OUI_NON_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
        method="filter_dossier_complet",
    )

    cofinancement = ModelMultipleChoiceFilter(
        label="Cofinancement",
        field_name="dossier_ds__demande_cofinancements",
        queryset=Cofinancement.objects.none(),
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    zonage = ModelMultipleChoiceFilter(
        label="Zonage",
        field_name="dossier_ds__projet_zonage",
        queryset=ProjetZonage.objects.none(),
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    contractualisation = ModelMultipleChoiceFilter(
        label="Contractualisation",
        field_name="dossier_ds__projet_contractualisation",
        queryset=ProjetContractualisation.objects.none(),
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

    epci = MultipleChoiceFilter(
        label="EPCI",
        field_name="dossier_ds__porteur_de_projet_epci",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    order = ProjetOrderingFilter(
        fields=SIMULATION_ORDERING_MAP,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    filter_territoire = staticmethod(filter_territoire)
    filter_boolean = staticmethod(filter_boolean)
    filter_dotation_sollicitee = staticmethod(filter_dotation_sollicitee)
    filter_dossier_complet = staticmethod(filter_dossier_complet)
    filter_search = staticmethod(
        make_filter_search(
            intitule_field="dossier_ds__projet_intitule",
            raison_sociale_field="dossier_ds__ds_demandeur__raison_sociale",
            ds_number_field="dossier_ds__ds_number",
        )
    )

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
            "search",
            "territoire",
            "epci",
            "categorie_detr",
            "categorie_dsil",
            "porteur",
            "dossier_complet",
            "status",
            "cout",
            "montant_demande",
            "montant_previsionnel",
            "budget_vert_demandeur",
            "budget_vert_instructeur",
            "dotation_sollicitee",
            "cofinancement",
            "zonage",
            "contractualisation",
            "date_depot",
            "date_debut",
            "date_achevement",
        )

    @property
    def qs(self):
        from gsl_projet.models import DotationProjet

        slug_filter = {"simulationprojet__simulation__slug": self.slug}
        simu_dp_qs = DotationProjet.active.filter(
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
