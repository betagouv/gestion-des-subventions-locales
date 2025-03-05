from django.db.models import Q
from django.forms import NumberInput, Select
from django_filters import (
    ChoiceFilter,
    FilterSet,
    MultipleChoiceFilter,
    NumberFilter,
)

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.models import Projet
from gsl_projet.services import ProjetService
from gsl_projet.utils.django_filters_custom_widget import CustomCheckboxSelectMultiple
from gsl_projet.utils.utils import order_couples_tuple_by_first_value


class ProjetFilters(FilterSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.get_filters()
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )

    dotation = ChoiceFilter(
        field_name="dossier_ds__demande_dispositif_sollicite",
        choices=(
            (Dossier.DOTATION_DETR, Dossier.DOTATION_DETR),
            (Dossier.DOTATION_DSIL, Dossier.DOTATION_DSIL),
        ),
        widget=Select(
            attrs={
                "class": "fr-select",
                "onchange": "this.form.submit()",
            }
        ),
        empty_label="Toutes les dotations",
        lookup_expr="contains",
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
            },
        ),
        empty_label="Tous les porteurs",
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

    ordered_status: tuple[str, ...] = (
        Projet.STATUS_PROCESSING,
        Projet.STATUS_REFUSED,
        Projet.STATUS_ACCEPTED,
        Projet.STATUS_DISMISSED,
    )

    status = MultipleChoiceFilter(
        field_name="status",
        choices=order_couples_tuple_by_first_value(
            Projet.STATUS_CHOICES, ordered_status
        ),
        widget=CustomCheckboxSelectMultiple(),
    )

    territoire = MultipleChoiceFilter(
        method="filter_territoire",
        choices=[],
        widget=CustomCheckboxSelectMultiple(),
    )

    def filter_territoire(self, queryset, _name, value):
        perimetres = set()
        for perimetre in Perimetre.objects.filter(id__in=value):
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
