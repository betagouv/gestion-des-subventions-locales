from django.db.models import Count, Exists, F, OuterRef, Q
from django.forms.utils import pretty_name
from django.utils.translation import gettext_lazy as _
from django_filters import (
    FilterSet,
    MultipleChoiceFilter,
    OrderingFilter,
    RangeFilter,
)

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import NaturePorteurProjet
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

    filter_dotation = staticmethod(filter_dotation)
    filter_territoire = staticmethod(filter_territoire)

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
            "dotation",
            "porteur",
            "categorie_detr",
            "categorie_dsil",
            "status",
            "cout",
            "montant_demande",
            "montant_retenu",
        )

    @property
    def qs(self):
        qs = super().qs
        if not qs.query.order_by:
            qs = qs.order_by(F("dossier_ds__ds_date_depot").desc(nulls_last=True))
        return qs
