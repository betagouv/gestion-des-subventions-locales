from django.db.models import Count, Exists, OuterRef, Q
from django.forms import NumberInput
from django_filters import (
    FilterSet,
    MultipleChoiceFilter,
    NumberFilter,
    OrderingFilter,
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
)
from gsl_projet.utils.utils import order_couples_tuple_by_first_value


class ProjetFilters(FilterSet):
    ORDERING_MAP = {
        "dossier_ds__ds_date_depot": "date",
        "dossier_ds__finance_cout_total": "cout",
        "demandeur__name": "demandeur",
    }

    order = OrderingFilter(
        fields=ORDERING_MAP,
        field_labels={
            "dossier_ds__ds_date_depot": "Date",
            "dossier_ds__finance_cout_total": "Coût total",
            "demandeur__name": "Demandeur",
        },
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    DOTATION_CHOICES = (
        (DOTATION_DETR, DOTATION_DETR),
        (DOTATION_DSIL, DOTATION_DSIL),
        (
            "DETR_et_DSIL",
            f"{DOTATION_DETR} et {DOTATION_DSIL}",
        ),
    )

    dotation = MultipleChoiceFilter(
        choices=DOTATION_CHOICES,
        widget=CustomCheckboxSelectMultiple(),
        method="filter_dotation",
    )

    def filter_dotation(self, queryset, _name, values):
        if not values:
            return queryset

        query = Q()

        queryset = queryset.annotate(
            detr_count=Count(
                "dotationprojet", filter=Q(dotationprojet__dotation="DETR")
            ),
            dsil_count=Count(
                "dotationprojet", filter=Q(dotationprojet__dotation="DSIL")
            ),
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

    montant_retenu_min = NumberFilter(
        method="filter_montant_retenu",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_retenu_max = NumberFilter(
        method="filter_montant_retenu",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    def filter_montant_retenu(self, queryset, _name, value):
        montant_min = self.data.get("montant_retenu_min")
        montant_max = self.data.get("montant_retenu_max")

        if not montant_min and not montant_max:
            return queryset

        dotation_qs = DotationProjet.objects.filter(projet=OuterRef("pk"))

        if montant_min:
            dotation_qs = dotation_qs.filter(
                programmation_projet__montant__gte=montant_min
            )
        if montant_max:
            dotation_qs = dotation_qs.filter(
                programmation_projet__montant__lte=montant_max
            )

        return queryset.annotate(match=Exists(dotation_qs)).filter(match=True)

    ordered_status: tuple[str, ...] = (
        PROJET_STATUS_PROCESSING,
        PROJET_STATUS_REFUSED,
        PROJET_STATUS_ACCEPTED,
        PROJET_STATUS_DISMISSED,
    )

    status = MultipleChoiceFilter(
        field_name="status",
        choices=order_couples_tuple_by_first_value(
            PROJET_STATUS_CHOICES, ordered_status
        ),
        widget=CustomCheckboxSelectMultiple(),
    )

    territoire = MultipleChoiceFilter(
        method="filter_territoire",
        choices=[],
        widget=CustomCheckboxSelectMultiple(),
    )

    def filter_territoire(self, queryset, _name, values: list[int]):
        perimetres = set()
        for perimetre in Perimetre.objects.filter(id__in=values):
            perimetres.add(perimetre)
            for child in perimetre.children():
                perimetres.add(child)
        return queryset.filter(perimetre__in=perimetres)

    categorie_detr = MultipleChoiceFilter(
        method="filter_categorie_detr",
        choices=[],
        widget=CustomCheckboxSelectMultiple(),
    )

    def filter_categorie_detr(self, queryset, _name, values: list[int]):
        return queryset.filter(dotationprojet__detr_categories__in=values)

    class Meta:
        model = Projet
        fields = (
            "dotation",
            "porteur",
            "cout_min",
            "cout_max",
            "montant_demande_min",
            "montant_demande_max",
            "montant_retenu_min",
            "montant_retenu_max",
            "status",
            "territoire",
            "categorie_detr",
        )

    @property
    def qs(self):
        self.queryset = Projet.objects.all()
        qs = super().qs
        if self.request.GET.get("order") in [None, ""]:
            qs = qs.order_by("-dossier_ds__ds_date_depot")
        return qs
