from django.db.models import Case, DecimalField, F, When
from django_filters import (
    ChoiceFilter,
    FilterSet,
    MultipleChoiceFilter,
    RangeFilter,
)

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import NaturePorteurProjet
from gsl_programmation.models import (
    Enveloppe,
    ProgrammationProjet,
)
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
    DsfrRangeWidget,
)
from gsl_projet.utils.projet_filters import ProjetOrderingFilter

PROGRAMMATION_ORDERING_MAP = {
    "dotation_projet__projet__dossier_ds__finance_cout_total": "cout",
    "dotation_projet__projet__demandeur__name": "demandeur",
    "montant": "montant",
    "dotation_projet__projet__dossier_ds__ds_number": "numero_dn",
    "dotation_projet__projet__dossier_ds__porteur_de_projet_arrondissement__name": "arrondissement",
    "dotation_projet__projet__dossier_ds__porteur_de_projet_nom": "nom_demandeur",
    "dotation_projet__projet__dossier_ds__demande_montant": "montant_sollicite",
    "dotation_projet__projet__dossier_ds__date_debut": "date_debut",
    "dotation_projet__projet__dossier_ds__date_achevement": "date_fin",
    "dotation_projet__projet__dossier_ds__porteur_de_projet_epci": "epci",
    "dotation_projet__assiette": "assiette",
    "prog_taux": "taux",
}


class ProgrammationProjetFilters(FilterSet):
    porteur = MultipleChoiceFilter(
        label="Demandeur",
        field_name="dotation_projet__projet__dossier_ds__porteur_de_projet_nature__type",
        choices=NaturePorteurProjet.TYPE_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    cout = RangeFilter(
        label="Coût total",
        field_name="dotation_projet__projet__dossier_ds__finance_cout_total",
        widget=DsfrRangeWidget(icon="fr-icon-coin-fill"),
    )

    montant_demande = RangeFilter(
        label="Montant demandé",
        field_name="dotation_projet__projet__dossier_ds__demande_montant",
        widget=DsfrRangeWidget(
            icon="fr-icon-money-euro-circle-fill",
            display_template="includes/_filter_montant_demande.html",
        ),
    )

    montant_retenu = RangeFilter(
        label="Montant retenu",
        field_name="montant",
        widget=DsfrRangeWidget(icon="fr-icon-money-euro-box-fill"),
    )

    status = MultipleChoiceFilter(
        label="Statut",
        field_name="status",
        choices=(ProgrammationProjet.STATUS_CHOICES),
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    territoire = MultipleChoiceFilter(
        method="filter_territoire",
        choices=[],
        widget=CustomCheckboxSelectMultiple(
            display_template="includes/_filter_territoire.html"
        ),
    )

    notified = ChoiceFilter(
        label="Demandeur notifié",
        method="filter_notified",
        choices=(("yes", "Oui"), ("no", "Non")),
        empty_label="Tous",
        widget=CustomSelectWidget,
    )

    def filter_territoire(self, queryset, _name, values: list[int]):
        result = queryset.none()
        for perimetre in Perimetre.objects.filter(id__in=values):
            result |= queryset.for_perimetre(perimetre)
        return result

    def filter_notified(self, queryset, _name, value: str):
        if value == "yes":
            return queryset.exclude(dotation_projet__projet__notified_at=None)
        elif value == "no":
            return queryset.filter(dotation_projet__projet__notified_at=None)
        else:
            return queryset

    order = ProjetOrderingFilter(
        fields=PROGRAMMATION_ORDERING_MAP,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    class Meta:
        model = ProgrammationProjet
        fields = (
            "territoire",
            "porteur",
            "notified",
            "cout",
            "montant_demande",
            "montant_retenu",
            "status",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
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
            .for_current_year()
        )

        try:
            self.enveloppe = enveloppe_qs.get(perimetre=self.perimetre)
        except Enveloppe.DoesNotExist:
            self.enveloppe = None

        qs = (
            super()
            .qs.filter(
                enveloppe__in=enveloppe_qs,
            )
            .for_perimetre(self.request.user.perimetre)
        )
        qs = qs.annotate(
            prog_taux=Case(
                When(
                    dotation_projet__assiette__gt=0,
                    then=F("montant") * 100.0 / F("dotation_projet__assiette"),
                ),
                When(
                    dotation_projet__projet__dossier_ds__finance_cout_total__gt=0,
                    then=F("montant")
                    * 100.0
                    / F("dotation_projet__projet__dossier_ds__finance_cout_total"),
                ),
                default=None,
                output_field=DecimalField(),
            ),
        )
        if not qs.query.order_by:
            qs = qs.order_by("-created_at")

        return qs
