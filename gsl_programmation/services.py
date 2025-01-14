from decimal import Decimal

from django.db.models import Case, F, Sum, When
from django.db.models.query import QuerySet

from gsl_programmation.models import SimulationProjet


class SimulationProjetService:
    @classmethod
    def update_status(cls, simulation_projet: SimulationProjet, new_status: str):
        simulation_projet.status = new_status
        simulation_projet.save()
        return simulation_projet

    @classmethod
    def update_taux(cls, simulation_projet: SimulationProjet, new_taux: float):
        new_montant = (
            simulation_projet.projet.assiette_or_cout_total * Decimal(new_taux) / 100
        )
        new_montant = round(new_montant, 2)

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()

    @classmethod
    def update_montant(cls, simulation_projet, new_montant: float):
        new_taux = (
            Decimal(new_montant)
            / Decimal(simulation_projet.projet.assiette_or_cout_total)
        ) * 100
        new_taux = round(new_taux, 2)
        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()


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
