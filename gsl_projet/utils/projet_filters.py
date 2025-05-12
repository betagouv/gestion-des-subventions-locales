from django.db.models import Q
from django.forms import NumberInput
from django_filters import (
    FilterSet,
    MultipleChoiceFilter,
    NumberFilter,
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
from gsl_projet.models import Projet
from gsl_projet.services.projet_services import ProjetService
from gsl_projet.utils.django_filters_custom_widget import CustomCheckboxSelectMultiple
from gsl_projet.utils.utils import order_couples_tuple_by_first_value


class ProjetFilters(FilterSet):
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

    # TODO dotation_pr use dotation_projet
    def filter_dotation(self, queryset, _name, values):
        if not values:
            return queryset

        query = Q()

        if DOTATION_DETR in values:
            if DOTATION_DSIL in values:
                if "DETR_et_DSIL" in values:
                    # Inclure "DETR" ou "DSIL"
                    query &= Q(
                        Q(
                            dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DETR
                        )
                        | Q(
                            dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DSIL
                        )
                    )
                else:
                    # Inclure "DETR" seul ou "DSIL" seul mais pas "DETR" et "DSIL" ensemble
                    query &= (
                        Q(
                            dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DETR
                        )
                        & ~Q(
                            dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DSIL
                        )
                    ) | (
                        Q(
                            dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DSIL
                        )
                        & ~Q(
                            dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DETR
                        )
                    )
            else:
                if "DETR_et_DSIL" in values:
                    # Inclure "DETR" seul ou "DETR_et_DSIL", mais exclure "DSIL" seul
                    query &= Q(
                        dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DETR
                    )

                if "DETR_et_DSIL" not in values:
                    # Inclure "DETR" mais exclure ceux qui contiennent "DSIL"
                    query &= Q(
                        dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DETR
                    ) & ~Q(
                        dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DSIL
                    )

        else:
            if DOTATION_DSIL in values:
                if "DETR_et_DSIL" in values:
                    # Inclure "DSIL" seul ou "DETR_et_DSIL", mais exclure "DETR" seul
                    query &= Q(
                        dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DSIL
                    )
                else:
                    # Inclure uniquement "DSIL" et exclure "DETR"
                    query &= Q(
                        dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DSIL
                    ) & ~Q(
                        dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DETR
                    )
            else:
                # Inclure seulement les projets double dotations "DETR" et "DSIL"
                query &= Q(
                    Q(dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DETR)
                    & Q(
                        dossier_ds__demande_dispositif_sollicite__icontains=DOTATION_DSIL
                    )
                )

        return queryset.filter(query)

    porteur = MultipleChoiceFilter(
        field_name="dossier_ds__porteur_de_projet_nature__type",
        choices=NaturePorteurProjet.TYPE_CHOICES,
        widget=CustomCheckboxSelectMultiple(),
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
        )

    @property
    def qs(self):
        self.queryset = Projet.objects.all()
        qs = super().qs
        qs = ProjetService.add_ordering_to_projets_qs(qs, self.request.GET.get("tri"))
        return qs
