from decimal import Decimal

from gsl_programmation.services.enveloppe_service import EnveloppeService
from gsl_simulation.models import SimulationProjet


class SimulationProjetService:
    @classmethod
    def _accept_a_simulation_projet(cls, simulation_projet: SimulationProjet):
        projet = simulation_projet.projet
        enveloppe = EnveloppeService.get_mother_enveloppe(simulation_projet.enveloppe)
        projet.accept(montant=simulation_projet.montant, enveloppe=enveloppe)

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def update_status(cls, simulation_projet: SimulationProjet, new_status: str):
        if new_status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet)

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
