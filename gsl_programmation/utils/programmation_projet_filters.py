from functools import cached_property

from django.db.models import Case, DecimalField, F, Q, When
from django_filters import (
    MultipleChoiceFilter,
    RangeFilter,
)

from gsl.core.models import Perimetre
from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from gsl.projet.models import EnveloppeProjet
from gsl.projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
    DsfrRangeWidget,
)
from gsl.projet.utils.projet_filters import (
    CommonFiltersFields,
    ProjetOrderingFilter,
    make_filter_search,
)
from gsl_demarches_simplifiees.models import (
    CategorieDetr,
    CategorieDsil,
    Cofinancement,
    Dossier,
    ProjetContractualisation,
    ProjetZonage,
)
from gsl_programmation.models import Enveloppe

PROGRAMMATION_ORDERING_MAP = {
    "projet__dossier_ds__finance_cout_total": "cout",
    "projet__dossier_ds__ds_demandeur__raison_sociale": "demandeur",
    "montant": "montant",
    "projet__dossier_ds__ds_number": "numero_dn",
    "projet__dossier_ds__porteur_de_projet_arrondissement__name": "arrondissement",
    "projet__dossier_ds__porteur_de_projet_nom": "nom_demandeur",
    "projet__dossier_ds__demande_montant": "montant_sollicite",
    "projet__dossier_ds__date_debut": "date_debut",
    "projet__dossier_ds__date_achevement": "date_fin",
    "projet__dossier_ds__porteur_de_projet_epci": "epci",
    "projet__dossier_ds__demande_priorite_dsil_detr": "priorite",
    "assiette": "assiette",
    "prog_taux": "taux",
    "_notification_status": "notification",
}


class ProgrammationFilters(CommonFiltersFields):
    # EnveloppeProjet reaches Projet via `projet__`, unlike ProjetFilters/
    # SimulationProjetFilters whose Meta.model is Projet directly; the common
    # fields' field_name is prefixed accordingly.
    dossier_field_prefix = "projet__"

    fixed_filter_fields = (
        "search",
        "categorie_detr",
        "categorie_dsil",
        "cout",
        "montant_demande",
        "montant_retenu",
    )

    montant_retenu = RangeFilter(
        label="Montant retenu",
        field_name="montant",
        widget=DsfrRangeWidget(icon="fr-icon-money-euro-box-fill"),
    )

    status = MultipleChoiceFilter(
        label="Statut",
        field_name="status",
        choices=tuple((status.value, status.label) for status in ProjetStatus.FINAL),
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    filter_search = staticmethod(
        make_filter_search(
            intitule_field="projet__dossier_ds__projet_intitule",
            raison_sociale_field="projet__dossier_ds__ds_demandeur__raison_sociale",
            ds_number_field="projet__dossier_ds__ds_number",
        )
    )

    order = ProjetOrderingFilter(
        fields=PROGRAMMATION_ORDERING_MAP,
        empty_label="Tri",
        widget=CustomSelectWidget,
    )

    class Meta:
        model = EnveloppeProjet
        fields = (
            "search",
            "territoire",
            "epci",
            "categorie_detr",
            "categorie_dsil",
            "porteur",
            "dossier_complet",
            "cout",
            "montant_demande",
            "montant_retenu",
            "dotation_sollicitee",
            "budget_vert_demandeur",
            "budget_vert_instructeur",
            "cofinancement",
            "zonage",
            "contractualisation",
            "status",
            "notification_status",
            "date_depot",
            "date_debut",
            "date_achevement",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Annotated here (not lazily in `qs`, unlike `prog_taux`) so it's
        # ready both for the notification_status filter and for sorting.
        self.queryset = self.queryset.annotate_notification_status()

        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].queryset = Perimetre.objects.filter(
                Q(id=perimetre.id) | Q(id__in=perimetre.children().values("id"))
            )

        dotation = self.request.resolver_match.kwargs.get("dotation")
        visible_dossiers = Dossier.objects.for_user(self.request.user)

        if dotation == DOTATION_DETR:
            self.filters["categorie_detr"].queryset = (
                CategorieDetr.objects.active()
                .filter(dossier__in=visible_dossiers)
                .distinct()
                .order_by("rank")
            )
        else:
            del self.filters["categorie_detr"]

        if dotation == DOTATION_DSIL:
            self.filters["categorie_dsil"].queryset = (
                CategorieDsil.objects.active()
                .filter(dossier__in=visible_dossiers)
                .distinct()
                .order_by("rank", "label")
            )
        else:
            del self.filters["categorie_dsil"]

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

        self.filters["epci"].extra["choices"] = lambda: tuple(
            (epci, epci.split(" - ", 1)[1] if " - " in epci else epci)
            for epci in visible_dossiers.values_list(
                "porteur_de_projet_epci", flat=True
            )
            .distinct()
            .order_by("porteur_de_projet_epci")
            if epci
        )

    @cached_property
    def perimetre(self) -> Perimetre:
        return self.request.user.perimetre

    @cached_property
    def dotation(self):
        return self.request.resolver_match.kwargs.get("dotation")

    @cached_property
    def _enveloppe_qs(self):
        return (
            Enveloppe.objects.select_related(
                "perimetre",
                "perimetre__region",
                "perimetre__departement",
                "perimetre__arrondissement",
            )
            .filter(dotation=self.dotation)
            .for_current_year()
        )

    @cached_property
    def enveloppe(self):
        try:
            return self._enveloppe_qs.get(perimetre=self.perimetre)
        except Enveloppe.DoesNotExist:
            return None

    @property
    def qs(self):
        qs = (
            super()
            .qs.filter(enveloppe__in=self._enveloppe_qs)
            .for_perimetre(self.perimetre)
        )
        qs = qs.annotate(
            prog_taux=Case(
                When(
                    assiette__gt=0,
                    then=F("montant") * 100.0 / F("assiette"),
                ),
                When(
                    projet__dossier_ds__finance_cout_total__gt=0,
                    then=F("montant")
                    * 100.0
                    / F("projet__dossier_ds__finance_cout_total"),
                ),
                default=None,
                output_field=DecimalField(),
            ),
        )
        if not qs.query.order_by:
            qs = qs.order_by("-date_programmation")

        return qs
