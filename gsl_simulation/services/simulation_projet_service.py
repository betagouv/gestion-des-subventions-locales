from decimal import Decimal

from gsl_simulation.models import SimulationProjet


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
