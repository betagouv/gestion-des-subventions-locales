from django.db.models import Count, Exists, F, OuterRef, Q
from django.forms.utils import pretty_name
from django.utils.translation import gettext_lazy as _
from django_filters import (
    DateFromToRangeFilter,
    FilterSet,
    MultipleChoiceFilter,
    OrderingFilter,
    RangeFilter,
)

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import Dossier, NaturePorteurProjet
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
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
    "demandeur__name": "demandeur",
    "dossier_ds__ds_number": "numero_dn",
    "dossier_ds__porteur_de_projet_arrondissement__name": "arrondissement",
    "dossier_ds__porteur_de_projet_nom": "nom_demandeur",
    "dossier_ds__demande_montant": "montant_sollicite",
    "dossier_ds__date_debut": "date_debut",
    "dossier_ds__date_achevement": "date_fin",
    "dossier_ds__porteur_de_projet_epci": "epci",
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


def filter_territoire(queryset, _name, values: list[int]):
    result = queryset.none()
    for perimetre in Perimetre.objects.filter(id__in=values):
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


def filter_dossier_complet(queryset, name, values):
    if not values:
        return queryset

    q = Q()
    if "oui" in values:
        q |= ~Q(**{name: Dossier.STATE_EN_CONSTRUCTION})
    if "non" in values:
        q |= Q(**{name: Dossier.STATE_EN_CONSTRUCTION})

    return queryset.filter(q)


class ProjetFilters(FilterSet):
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

    montant_retenu = RangeFilter(
        label="Montant retenu",
        method="filter_montant_retenu",
        widget=DsfrRangeWidget(icon="fr-icon-money-euro-box-fill"),
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

    categorie_detr = MultipleChoiceFilter(
        label="Catégorie DETR",
        field_name="dossier_ds__demande_categorie_detr",
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

    categorie_dsil = MultipleChoiceFilter(
        label="Catégorie DSIL",
        field_name="dossier_ds__demande_categorie_dsil",
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

    territoire = MultipleChoiceFilter(
        method="filter_territoire",
        choices=[],
        widget=CustomCheckboxSelectMultiple(
            display_template="includes/_filter_territoire.html"
        ),
    )

    epci = MultipleChoiceFilter(
        label="EPCI",
        field_name="dossier_ds__porteur_de_projet_epci",
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

    cofinancement = MultipleChoiceFilter(
        label="Cofinancement",
        field_name="dossier_ds__demande_cofinancements",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    zonage = MultipleChoiceFilter(
        label="Zonage",
        field_name="dossier_ds__projet_zonage",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    contractualisation = MultipleChoiceFilter(
        label="Contractualisation",
        field_name="dossier_ds__projet_contractualisation",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

    filter_dotation = staticmethod(filter_dotation)
    filter_territoire = staticmethod(filter_territoire)
    filter_boolean = staticmethod(filter_boolean)
    filter_dotation_sollicitee = staticmethod(filter_dotation_sollicitee)
    filter_dossier_complet = staticmethod(filter_dossier_complet)

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

    class Meta:
        model = Projet
        fields = (
            "territoire",
            "epci",
            "dotation",
            "porteur",
            "categorie_detr",
            "categorie_dsil",
            "status",
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
