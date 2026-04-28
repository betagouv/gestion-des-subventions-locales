from django.db.models import Case, DecimalField, F, When
from django_filters import (
    ChoiceFilter,
    DateFromToRangeFilter,
    FilterSet,
    MultipleChoiceFilter,
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
from gsl_programmation.models import (
    Enveloppe,
    ProgrammationProjet,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.utils.django_filters_custom_widget import (
    CustomCheckboxSelectMultiple,
    CustomSelectWidget,
    DsfrDateRangeWidget,
    DsfrRangeWidget,
)
from gsl_projet.utils.projet_filters import (
    DOTATION_SOLLICITEE_CHOICES,
    OUI_NON_CHOICES,
    ProjetOrderingFilter,
    filter_boolean,
    filter_dossier_complet,
    filter_dotation_sollicitee,
)

PROGRAMMATION_ORDERING_MAP = {
    "dotation_projet__projet__dossier_ds__finance_cout_total": "cout",
    "dotation_projet__projet__dossier_ds__ds_demandeur__raison_sociale": "demandeur",
    "montant": "montant",
    "dotation_projet__projet__dossier_ds__ds_number": "numero_dn",
    "dotation_projet__projet__dossier_ds__porteur_de_projet_arrondissement__name": "arrondissement",
    "dotation_projet__projet__dossier_ds__porteur_de_projet_nom": "nom_demandeur",
    "dotation_projet__projet__dossier_ds__demande_montant": "montant_sollicite",
    "dotation_projet__projet__dossier_ds__date_debut": "date_debut",
    "dotation_projet__projet__dossier_ds__date_achevement": "date_fin",
    "dotation_projet__projet__dossier_ds__porteur_de_projet_epci": "epci",
    "dotation_projet__projet__dossier_ds__demande_priorite_dsil_detr": "priorite",
    "dotation_projet__assiette": "assiette",
    "prog_taux": "taux",
}


class ProgrammationProjetFilters(FilterSet):
    categorie_detr = MultipleChoiceFilter(
        label="Catégorie DETR",
        field_name="dotation_projet__projet__dossier_ds__demande_categorie_detr",
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

    categorie_dsil = MultipleChoiceFilter(
        label="Catégorie DSIL",
        field_name="dotation_projet__projet__dossier_ds__demande_categorie_dsil",
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

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

    budget_vert_demandeur = MultipleChoiceFilter(
        label="Budget vert (demandeur)",
        field_name="dotation_projet__projet__dossier_ds__environnement_transition_eco",
        choices=OUI_NON_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
        method="filter_boolean",
    )

    budget_vert_instructeur = MultipleChoiceFilter(
        label="Budget vert (instructeur)",
        field_name="dotation_projet__projet__is_budget_vert",
        choices=OUI_NON_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
        method="filter_boolean",
    )

    dotation_sollicitee = MultipleChoiceFilter(
        label="Dotation sollicitée",
        field_name="dotation_projet__projet__dossier_ds__demande_dispositif_sollicite",
        choices=DOTATION_SOLLICITEE_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
        method="filter_dotation_sollicitee",
    )

    dossier_complet = MultipleChoiceFilter(
        label="Dossier complet",
        field_name="dotation_projet__projet__dossier_ds__ds_state",
        choices=OUI_NON_CHOICES,
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
        method="filter_dossier_complet",
    )

    cofinancement = MultipleChoiceFilter(
        label="Cofinancement",
        field_name="dotation_projet__projet__dossier_ds__demande_cofinancements",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    zonage = MultipleChoiceFilter(
        label="Zonage",
        field_name="dotation_projet__projet__dossier_ds__projet_zonage",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    contractualisation = MultipleChoiceFilter(
        label="Contractualisation",
        field_name="dotation_projet__projet__dossier_ds__projet_contractualisation",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Toutes"),
    )

    epci = MultipleChoiceFilter(
        label="EPCI",
        field_name="dotation_projet__projet__dossier_ds__porteur_de_projet_epci",
        choices=[],
        widget=CustomCheckboxSelectMultiple(placeholder="Tous"),
    )

    filter_boolean = staticmethod(filter_boolean)
    filter_dotation_sollicitee = staticmethod(filter_dotation_sollicitee)
    filter_dossier_complet = staticmethod(filter_dossier_complet)

    date_depot = DateFromToRangeFilter(
        label="Date de dépôt",
        field_name="dotation_projet__projet__dossier_ds__ds_date_depot__date",
        widget=DsfrDateRangeWidget(icon="fr-icon-calendar-line"),
    )

    date_debut = DateFromToRangeFilter(
        label="Date de commencement",
        field_name="dotation_projet__projet__dossier_ds__date_debut",
        widget=DsfrDateRangeWidget(icon="fr-icon-calendar-line"),
    )

    date_achevement = DateFromToRangeFilter(
        label="Date d'achèvement",
        field_name="dotation_projet__projet__dossier_ds__date_achevement",
        widget=DsfrDateRangeWidget(icon="fr-icon-calendar-line"),
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
            "epci",
            "categorie_detr",
            "categorie_dsil",
            "porteur",
            "dossier_complet",
            "notified",
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
            "date_depot",
            "date_debut",
            "date_achevement",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self.request, "user") and self.request.user.perimetre:
            perimetre = self.request.user.perimetre
            self.filters["territoire"].extra["choices"] = tuple(
                (p.id, p.entity_name) for p in (perimetre, *perimetre.children())
            )

        dotation = self.request.resolver_match.kwargs.get("dotation")
        visible_dossiers = Dossier.objects.for_user(self.request.user)

        if dotation == DOTATION_DETR:
            self.filters["categorie_detr"].extra["choices"] = tuple(
                (str(c.id), c.complete_label)
                for c in CategorieDetr.objects.active()
                .filter(dossier__in=visible_dossiers)
                .distinct()
                .order_by("rank")
            )
        else:
            del self.filters["categorie_detr"]

        if dotation == DOTATION_DSIL:
            self.filters["categorie_dsil"].extra["choices"] = tuple(
                (str(c.id), c.label)
                for c in CategorieDsil.objects.active()
                .filter(dossier__in=visible_dossiers)
                .distinct()
                .order_by("rank", "label")
            )
        else:
            del self.filters["categorie_dsil"]

        self.filters["cofinancement"].extra["choices"] = tuple(
            (str(c.id), c.label)
            for c in Cofinancement.objects.filter(dossier__in=visible_dossiers)
            .distinct()
            .order_by("id")
        )

        self.filters["zonage"].extra["choices"] = tuple(
            (str(z.id), z.label)
            for z in ProjetZonage.objects.filter(dossier__in=visible_dossiers)
            .distinct()
            .order_by("id")
        )

        self.filters["contractualisation"].extra["choices"] = tuple(
            (str(c.id), c.label)
            for c in ProjetContractualisation.objects.filter(
                dossier__in=visible_dossiers
            )
            .distinct()
            .order_by("id")
        )

        self.filters["epci"].extra["choices"] = tuple(
            (epci, epci.split(" - ", 1)[1] if " - " in epci else epci)
            for epci in visible_dossiers.values_list(
                "porteur_de_projet_epci", flat=True
            )
            .distinct()
            .order_by("porteur_de_projet_epci")
            if epci
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
