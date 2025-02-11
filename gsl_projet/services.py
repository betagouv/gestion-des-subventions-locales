from django.db.models import Case, F, Sum, When
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
