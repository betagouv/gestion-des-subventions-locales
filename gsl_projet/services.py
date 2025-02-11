from django.db.models import Case, F, Q, Sum, When
from django.db.models.query import QuerySet

from gsl_demarches_simplifiees.models import NaturePorteurProjet


class ProjetService:
    @classmethod
    def get_total_cost(cls, projet_qs: QuerySet):
        projets = projet_qs.annotate(
            calculed_cost=Case(
                When(assiette__isnull=False, then=F("assiette")),
                default=F("dossier_ds__finance_cout_total"),
            )
        )

        return projets.aggregate(total=Sum("calculed_cost"))["total"]

    @classmethod
    def get_total_amount_asked(cls, projet_qs: QuerySet):
        return projet_qs.aggregate(Sum("dossier_ds__demande_montant"))[
            "dossier_ds__demande_montant__sum"
        ]

    @classmethod
    def get_total_amount_granted(cls, projet_qs: QuerySet):
        return projet_qs.aggregate(Sum("simulationprojet__montant"))[
            "simulationprojet__montant__sum"
        ]

    PORTEUR_MAPPINGS = {
        "EPCI": NaturePorteurProjet.EPCI_NATURES,
        "Communes": NaturePorteurProjet.COMMUNE_NATURES,
    }

    @classmethod
    def add_filters_to_projets_qs(cls, qs, filters: dict):
        dotation = filters.get("dotation")
        if dotation:
            qs = qs.filter(dossier_ds__demande_dispositif_sollicite=dotation)

        cout_min = filters.get("cout_min")
        if cout_min and cout_min.isnumeric():
            qs = qs.filter(
                Q(assiette__isnull=False, assiette__gte=cout_min)
                | Q(assiette__isnull=True, dossier_ds__finance_cout_total__gte=cout_min)
            )

        cout_max = filters.get("cout_max")
        if cout_max and cout_max.isnumeric():
            qs = qs.filter(
                Q(assiette__isnull=False, assiette__lte=cout_max)
                | Q(assiette__isnull=True, dossier_ds__finance_cout_total__lte=cout_max)
            )

        montant_demande_min = filters.get("montant_demande_min")
        if montant_demande_min and montant_demande_min.isnumeric():
            qs = qs.filter(dossier_ds__demande_montant__gte=montant_demande_min)

        montant_demande_max = filters.get("montant_demande_max")
        if montant_demande_max and montant_demande_max.isnumeric():
            qs = qs.filter(dossier_ds__demande_montant__lte=montant_demande_max)

        montant_previsionnel_min = filters.get("montant_previsionnel_min")
        if montant_previsionnel_min and montant_previsionnel_min.isnumeric():
            qs = qs.filter(simulationprojet__montant__gte=montant_previsionnel_min)

        montant_previsionnel_max = filters.get("montant_previsionnel_max")
        if montant_previsionnel_max and montant_previsionnel_max.isnumeric():
            qs = qs.filter(simulationprojet__montant__lte=montant_previsionnel_max)

        porteur = filters.get("porteur")
        if porteur in cls.PORTEUR_MAPPINGS:
            qs = qs.filter(
                dossier_ds__porteur_de_projet_nature__label__in=cls.PORTEUR_MAPPINGS.get(
                    porteur
                )
            )

        return qs

    @classmethod
    def add_ordering_to_projets_qs(cls, qs, ordering):
        default_ordering = "-dossier_ds__ds_date_depot"
        qs = qs.order_by(default_ordering)

        ordering_arg = cls.get_ordering_arg(ordering)
        if ordering_arg:
            qs = qs.order_by(ordering_arg)
        return qs

    @classmethod
    def get_ordering_arg(cls, ordering):
        ordering_map = {
            "date_desc": "-dossier_ds__ds_date_depot",
            "date_asc": "dossier_ds__ds_date_depot",
            "cout_desc": "-dossier_ds__finance_cout_total",
            "cout_asc": "dossier_ds__finance_cout_total",
            "commune_desc": "-address__commune__name",
            "commune_asc": "address__commune__name",
        }

        return ordering_map.get(ordering, None)
