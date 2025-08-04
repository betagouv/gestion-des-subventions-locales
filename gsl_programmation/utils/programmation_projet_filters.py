from django.forms import NumberInput, Select
from django_filters import (
    ChoiceFilter,
    FilterSet,
    MultipleChoiceFilter,
    NumberFilter,
    OrderingFilter,
)

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.models import CategorieDetr
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
)


class ProgrammationProjetFilters(FilterSet):
    filterset = (
        "territoire",
        "porteur",
        "categorie_detr",
        "to_notify",
        "cout_total",
        "montant_demande",
        "montant_retenu",
        "status",
    )

    porteur = MultipleChoiceFilter(
        field_name="dotation_projet__projet__dossier_ds__porteur_de_projet_nature__type",
        choices=NaturePorteurProjet.TYPE_CHOICES,
        widget=CustomCheckboxSelectMultiple(),
    )

    cout_min = NumberFilter(
        field_name="dotation_projet__projet__dossier_ds__finance_cout_total",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    cout_max = NumberFilter(
        field_name="dotation_projet__projet__dossier_ds__finance_cout_total",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_demande_max = NumberFilter(
        field_name="dotation_projet__projet__dossier_ds__demande_montant",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_demande_min = NumberFilter(
        field_name="dotation_projet__projet__dossier_ds__demande_montant",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_retenu_min = NumberFilter(
        field_name="montant",
        lookup_expr="gte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    montant_retenu_max = NumberFilter(
        field_name="montant",
        lookup_expr="lte",
        widget=NumberInput(
            attrs={"class": "fr-input", "min": "0"},
        ),
    )

    status = MultipleChoiceFilter(
        field_name="status",
        choices=(ProgrammationProjet.STATUS_CHOICES),
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
        return queryset.filter(dotation_projet__projet__perimetre__in=perimetres)

    categorie_detr = MultipleChoiceFilter(
        method="filter_categorie_detr",
        choices=[],
        widget=CustomCheckboxSelectMultiple(),
    )

    def filter_categorie_detr(self, queryset, _name, values: list[int]):
        return queryset.filter(dotation_projet__detr_categories__in=values)

    to_notify = ChoiceFilter(
        method="filter_to_notify",
        choices=(("yes", "Oui"), ("no", "Non")),
        empty_label="Tous",
        widget=Select(
            attrs={"class": "fr-select"},
        ),
    )

    def filter_to_notify(self, queryset, _name, value: str):
        if value == "yes":
            return queryset.filter(
                notified_at=None, status=ProgrammationProjet.STATUS_ACCEPTED
            )
        elif value == "no":
            return queryset.exclude(
                notified_at=None, status=ProgrammationProjet.STATUS_ACCEPTED
            )
        else:
            return queryset

    ORDERING_MAP = {
        "montant": "montant",
        "dotation_projet__projet__dossier_ds__finance_cout_total": "cout",
        "dotation_projet__projet__demandeur__name": "demandeur",
    }

    order = OrderingFilter(
        fields=ORDERING_MAP,
        field_labels={
            "montant": "Montant",
            "dotation_projet__projet__dossier_ds__finance_cout_total": "Coût",
            "dotation_projet__projet__demandeur__name": "Demandeur",
        },
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    class Meta:
        model = ProgrammationProjet
        fields = (
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
            "to_notify",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )
            if perimetre.departement:
                self.filters["categorie_detr"].extra["choices"] = tuple(
                    (c.id, c.libelle)
                    for c in CategorieDetr.objects.current_for_departement(
                        perimetre.departement
                    )
                )

    @property
    def qs(self):
        self.perimetre: Perimetre = self.request.user.perimetre
        self.dotation = self.request.resolver_match.kwargs.get("dotation")

        enveloppe_qs = (
            Enveloppe.objects.select_related(
                "perimetre",
                "perimetre__region",
                "perimetre__departement",
                "perimetre__arrondissement",
            )
            .filter(dotation=self.dotation)
            .order_by("-annee")
        )

        self.enveloppe = self._get_enveloppe_from_user_perimetre(
            self.perimetre, enveloppe_qs
        )
        qs = (
            super()
            .qs.for_enveloppe(enveloppe=self.enveloppe)
            .select_related(
                "dotation_projet",
                "dotation_projet__projet",
                "dotation_projet__projet__dossier_ds",
                "dotation_projet__projet__perimetre",
                "dotation_projet__projet__demandeur",
                "enveloppe",
                "enveloppe__perimetre",
            )
            .prefetch_related("dotation_projet__detr_categories")
        )
        if not qs.query.order_by:
            qs = qs.order_by("-created_at")

        return qs

    def _get_enveloppe_from_user_perimetre(self, perimetre, enveloppe_qs):
        """
        Returns the enveloppe corresponding to the user's perimetre.
        If no enveloppe is found, it returns None.
        """
        if not perimetre:
            return enveloppe_qs.first()

        perimetre_enveloppe_qs = enveloppe_qs.filter(perimetre=perimetre)
        enveloppe = perimetre_enveloppe_qs.first()
        if enveloppe is not None:
            return enveloppe

        perimetre_enveloppe_qs = enveloppe_qs.filter(
            perimetre__departement=perimetre.departement
        )
        enveloppe = perimetre_enveloppe_qs.first()
        if enveloppe is not None:
            return enveloppe

        perimetre_enveloppe_qs = enveloppe_qs.filter(perimetre__region=perimetre.region)
        enveloppe = perimetre_enveloppe_qs.first()
        if enveloppe is not None:
            return enveloppe

        return Enveloppe.objects.none()
