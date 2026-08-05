from django import forms
from django.db import connection
from django.db.models import CharField, Count, Exists, F, Func, OuterRef, Q, Value
from django.db.models.functions import Cast
from django.forms.utils import pretty_name
from django.utils.translation import gettext_lazy as _
from django_filters import (
    CharFilter,
    DateFromToRangeFilter,
    FilterSet,
    ModelMultipleChoiceFilter,
    MultipleChoiceFilter,
    OrderingFilter,
    RangeFilter,
)

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    CategorieDsil,
    Cofinancement,
    Dossier,
    NaturePorteurProjet,
    ProjetContractualisation,
    ProjetZonage,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    NOTIFICATION_STATUS_CHOICES,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_CHOICES,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
    DsfrDateRangeWidget,
    DsfrRangeWidget,
)
from gsl_projet.utils.utils import order_couples_tuple_by_first_value


class LabelFromInstanceField(forms.ModelMultipleChoiceField):
    """ModelMultipleChoiceField that calls a configurable attribute/property
    for the option label, so we can use complete_label, entity_name, etc."""

    def __init__(self, *args, label_attr="label", **kwargs):
        self.label_attr = label_attr
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        return getattr(obj, self.label_attr)


class LabelFromInstanceFilter(ModelMultipleChoiceFilter):
    field_class = LabelFromInstanceField


class ProjetOrderingFilter(OrderingFilter):
    def build_choices(self, fields, labels):
        return [
            (
                labels.get(field, _(pretty_name(field))),
                (
                    (
                        (f"-{param}", "La plus récente"),
                        (param, "La plus ancienne"),
                    )
                    if param in {"date", "date_debut", "date_fin"}
                    else (
                        (param, "Croissant"),
                        (f"-{param}", "Décroissant"),
                    )
                ),
            )
            for field, param in fields.items()
        ]

    def get_ordering_value(self, param):
        descending = param.startswith("-")
        param = param[1:] if descending else param
        field_name = self.param_map.get(param, param)

        return (
            F(field_name).desc(nulls_last=True)
            if descending
            else F(field_name).asc(nulls_last=True)
        )


DOTATION_CHOICES = (
    (DOTATION_DETR, DOTATION_DETR),
    (DOTATION_DSIL, DOTATION_DSIL),
    (
        "DETR_et_DSIL",
        f"{DOTATION_DETR} et {DOTATION_DSIL}",
    ),
)

ORDERING_MAP = {
    "dossier_ds__ds_date_depot": "date",
    "dossier_ds__finance_cout_total": "cout",
    "dossier_ds__ds_demandeur__raison_sociale": "demandeur",
    "dossier_ds__ds_number": "numero_dn",
    "dossier_ds__porteur_de_projet_arrondissement__name": "arrondissement",
    "dossier_ds__porteur_de_projet_nom": "nom_demandeur",
    "dossier_ds__demande_montant": "montant_sollicite",
    "dossier_ds__date_debut": "date_debut",
    "dossier_ds__date_achevement": "date_fin",
    "dossier_ds__porteur_de_projet_epci": "epci",
    "dossier_ds__demande_priorite_dsil_detr": "priorite",
}


def filter_dotation(queryset, _name, values):
    if not values:
        return queryset

    query = Q()

    queryset = queryset.annotate(
        detr_count=Count("dotationprojet", filter=Q(dotationprojet__dotation="DETR")),
        dsil_count=Count("dotationprojet", filter=Q(dotationprojet__dotation="DSIL")),
    )

    if DOTATION_DETR in values:
        if DOTATION_DSIL in values:
            if "DETR_et_DSIL" in values:
                # Inclure "DETR" ou "DSIL"
                query &= Q(detr_count__gt=0) | Q(dsil_count__gt=0)
            else:
                # Inclure "DETR" seul ou "DSIL" seul mais pas "DETR" et "DSIL" ensemble
                query &= Q(detr_count__gt=0, dsil_count=0) | Q(
                    detr_count=0, dsil_count__gt=0
                )
        else:
            if "DETR_et_DSIL" in values:
                # Inclure "DETR" seul ou "DETR_et_DSIL", mais exclure "DSIL" seul
                query &= Q(detr_count__gt=0)
            if "DETR_et_DSIL" not in values:
                # Inclure "DETR" mais exclure ceux qui contiennent "DSIL"
                query &= Q(detr_count__gt=0, dsil_count=0)
    else:
        if DOTATION_DSIL in values:
            if "DETR_et_DSIL" in values:
                # Inclure "DSIL" seul ou "DETR_et_DSIL", mais exclure "DETR" seul
                query &= Q(dsil_count__gt=0)
            else:
                # Inclure uniquement "DSIL" et exclure "DETR"
                query &= Q(detr_count=0, dsil_count__gt=0)

        else:
            # Inclure seulement les projets double dotations "DETR" et "DSIL"
            query &= Q(detr_count__gt=0, dsil_count__gt=0)

    return queryset.filter(query)


def filter_territoire(queryset, _name, values):
    if not values:
        return queryset
    result = queryset.none()
    for perimetre in values:
        result |= queryset.for_perimetre(perimetre)
    return result


OUI_NON_CHOICES = (
    ("oui", "Oui"),
    ("non", "Non"),
)

DOTATION_SOLLICITEE_CHOICES = (
    ("detr_uniquement", "DETR uniquement"),
    ("dsil_uniquement", "DSIL uniquement"),
    ("detr_et_dsil", "DETR et DSIL"),
)


def filter_boolean(queryset, name, values):
    q = Q()
    if "oui" in values:
        q |= Q(**{name: True})
    if "non" in values:
        q |= Q(**{name: False})
    return queryset.filter(q)


def filter_dotation_sollicitee(queryset, name, values):
    if not values:
        return queryset

    q = Q()
    contains_detr = Q(**{f"{name}__icontains": "DETR"})
    contains_dsil = Q(**{f"{name}__icontains": "DSIL"})

    if "detr_uniquement" in values:
        q |= contains_detr & ~contains_dsil
    if "dsil_uniquement" in values:
        q |= ~contains_detr & contains_dsil
    if "detr_et_dsil" in values:
        q |= contains_detr & contains_dsil

    return queryset.filter(q)


def make_filter_search(intitule_field, raison_sociale_field, ds_number_field):
    """Build a CharFilter `method` that searches across project title, applicant
    name and dossier number. Uses trigram similarity on PostgreSQL, icontains
    on other backends (test sandbox uses SQLite)."""

    def filter_search(queryset, _name, value):
        value = (value or "").strip()
        if not value:
            return queryset

        if connection.vendor == "postgresql":
            from django.contrib.postgres.search import TrigramWordSimilarity

            def _unaccent(expr):
                return Func(expr, function="f_unaccent")

            queryset = queryset.annotate(
                _search_sim_intitule=TrigramWordSimilarity(
                    _unaccent(Value(value)), _unaccent(F(intitule_field))
                ),
                _search_sim_demandeur=TrigramWordSimilarity(
                    _unaccent(Value(value)), _unaccent(F(raison_sociale_field))
                ),
            )
            q = Q(_search_sim_intitule__gte=0.6) | Q(_search_sim_demandeur__gte=0.6)
        else:
            q = Q(**{f"{intitule_field}__icontains": value}) | Q(
                **{f"{raison_sociale_field}__icontains": value}
            )

        if value.isdigit():
            queryset = queryset.annotate(
                _search_ds_number_str=Cast(F(ds_number_field), output_field=CharField())
            )
            q |= Q(_search_ds_number_str__contains=value)

        return queryset.filter(q).distinct()

    return filter_search


def filter_dossier_complet(queryset, name, values):
    if not values:
        return queryset

    q = Q()
    if "oui" in values:
        q |= ~Q(**{name: Dossier.STATE_EN_CONSTRUCTION})
    if "non" in values:
        q |= Q(**{name: Dossier.STATE_EN_CONSTRUCTION})

    return queryset.filter(q)


class FixedFilterFieldsMixin:
    """Filters always rendered in the top fixed row, in display order.
    Names absent from a given FilterSet are skipped by the template."""

    fixed_filter_fields = (
        "search",
        "categorie_detr",
        "cout",
        "montant_demande",
        "montant_retenu",
    )

    @property
    def fixed_fields(self):
        """Bound fields for the fixed top row, in display order, skipping absent names."""
        return [
            self.form[name]
            for name in self.fixed_filter_fields
            if name in self.form.fields
        ]


class CommonFiltersFields(FixedFilterFieldsMixin, FilterSet):
    """Shared fields for ProjetFilters, SimulationProjetFilters (both
    Meta.model = Projet) and ProgrammationProjetFilters (Meta.model =
    ProgrammationProjet). `field_name`s below are declared relative to
    Projet; ProgrammationProjetFilters sets `dossier_field_prefix` to reach
    Projet through its own relation, prepended in `__init__`."""

    dossier_field_prefix = ""

    # Filters whose `field_name` is relative to Projet and needs
    # `dossier_field_prefix` prepended for FilterSets not based on it.
    prefixable_filters = (
        "categorie_detr",
        "categorie_dsil",
        "porteur",
        "cout",
        "montant_demande",
        "date_depot",
        "date_debut",
        "date_achevement",
        "budget_vert_demandeur",
        "budget_vert_instructeur",
        "dotation_sollicitee",
        "dossier_complet",
        "cofinancement",
        "zonage",
        "contractualisation",
        "epci",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.dossier_field_prefix:
            for name in self.prefixable_filters:
                filter_ = self.filters.get(name)
                if filter_ is not None:
                    filter_.field_name = self.dossier_field_prefix + filter_.field_name

    notification_status = MultipleChoiceFilter(
        label="Statut de notification",
        field_name="_notification_status",
        choices=NOTIFICATION_STATUS_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    search = CharFilter(
        label="Recherche",
        method="filter_search",
    )

    territoire = LabelFromInstanceFilter(
        label="Territoire",
        method="filter_territoire",
        queryset=Perimetre.objects.none(),
        widget=CustomCheckboxSelectMultiple(
            display_template="includes/_filter_territoire.html",
            label_attr="entity_name",
        ),
        label_attr="entity_name",
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

    epci = MultipleChoiceFilter(
        label="EPCI",
        field_name="dossier_ds__porteur_de_projet_epci",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
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

    filter_boolean = staticmethod(filter_boolean)
    filter_dotation_sollicitee = staticmethod(filter_dotation_sollicitee)
    filter_dossier_complet = staticmethod(filter_dossier_complet)
    filter_territoire = staticmethod(filter_territoire)


class ProjetFilters(CommonFiltersFields):
    # Overrides the common field to use the `Exists`-based method: a plain
    # Projet has no single `_notification_status` annotation to look up
    # (unlike SimulationProjetFilters/ProgrammationProjetFilters, whose
    # queryset is already scoped to one dotation).
    notification_status = MultipleChoiceFilter(
        label="Statut de notification",
        method="filter_notification_status",
        choices=NOTIFICATION_STATUS_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    order = ProjetOrderingFilter(
        fields=ORDERING_MAP,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    dotation = MultipleChoiceFilter(
        label="Dotation",
        choices=DOTATION_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes les dotations"),
        method="filter_dotation",
    )

    montant_retenu = RangeFilter(
        label="Montant retenu",
        method="filter_montant_retenu",
        widget=DsfrRangeWidget(icon="fr-icon-money-euro-box-fill"),
    )

    ordered_status: tuple[str, ...] = (
        PROJET_STATUS_PROCESSING,
        PROJET_STATUS_REFUSED,
        PROJET_STATUS_ACCEPTED,
        PROJET_STATUS_DISMISSED,
    )

    status = MultipleChoiceFilter(
        label="Statut",
        method="filter_status",
        choices=order_couples_tuple_by_first_value(
            PROJET_STATUS_CHOICES, ordered_status
        ),
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    filter_dotation = staticmethod(filter_dotation)
    filter_search = staticmethod(
        make_filter_search(
            intitule_field="dossier_ds__projet_intitule",
            raison_sociale_field="dossier_ds__ds_demandeur__raison_sociale",
            ds_number_field="dossier_ds__ds_number",
        )
    )

    def filter_montant_retenu(self, queryset, _name, value):
        dotation_qs = DotationProjet.objects.filter(projet=OuterRef("pk"))
        if value.start is not None:
            dotation_qs = dotation_qs.filter(
                programmation_projet__montant__gte=value.start
            )
        if value.stop is not None:
            dotation_qs = dotation_qs.filter(
                programmation_projet__montant__lte=value.stop
            )
        return queryset.annotate(match=Exists(dotation_qs)).filter(match=True)

    def filter_status(self, queryset, _name, values: list[str]):
        return queryset.annotate_status().filter(_status__in=values)

    def filter_notification_status(self, queryset, _name, values: list[str]):
        # Unlike `status`, this matches a projet as soon as ONE of its
        # dotations has the selected notification status, rather than
        # reducing to a single aggregated value first.
        dotation_qs = DotationProjet.objects.annotate_notification_status().filter(
            projet=OuterRef("pk"), _notification_status__in=values
        )
        return queryset.filter(Exists(dotation_qs))

    class Meta:
        model = Projet
        fields = (
            "search",
            "territoire",
            "epci",
            "dotation",
            "porteur",
            "categorie_detr",
            "categorie_dsil",
            "status",
            "notification_status",
            "budget_vert_demandeur",
            "budget_vert_instructeur",
            "dotation_sollicitee",
            "dossier_complet",
            "cofinancement",
            "zonage",
            "contractualisation",
            "cout",
            "montant_demande",
            "montant_retenu",
            "date_depot",
            "date_debut",
            "date_achevement",
        )

    @property
    def qs(self):
        qs = super().qs
        if not qs.query.order_by:
            qs = qs.order_by(F("dossier_ds__ds_date_depot").desc(nulls_last=True))
        return qs
