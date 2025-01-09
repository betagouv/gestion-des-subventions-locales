from decimal import Decimal


class SimulationProjetService:
    @classmethod
    def _update_simulation_projet_status(self, simulation_projet, new_status):
        simulation_projet.status = new_status
        simulation_projet.save()
        return simulation_projet

    @classmethod
    def _update_simulation_projet_taux_or_montant(
        self, simulation_projet, new_taux, new_montant
    ):
        if new_taux is not None:
            new_montant = (
                simulation_projet.projet.assiette_or_cout_total
                * Decimal(new_taux)
                / 100
            )
        else:
            new_taux = (
                Decimal(new_montant)
                / Decimal(simulation_projet.projet.assiette_or_cout_total)
            ) * 100
            new_taux = round(new_taux, 2)

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()
