from decimal import Decimal

from gsl_core.models import Perimetre
from gsl_projet.models import Projet
from gsl_projet.services import ProjetService
from gsl_simulation.models import Simulation, SimulationProjet


class SimulationProjetService:
    @classmethod
    def create_or_update_simulation_projets_from_projet(cls, projet: Projet):
        simulation_projets = SimulationProjet.objects.filter(projet=projet)
        for simulation_projet in simulation_projets:
            cls.create_or_update_simulation_projet_from_projet(
                projet, simulation_projet.simulation_id
            )

    @classmethod
    def create_or_update_simulation_projet_from_projet(
        cls, projet: Projet, simulation_id: int
    ):
        try:
            simulation_projet = SimulationProjet.objects.get(
                projet=projet, simulation_id=simulation_id
            )
        except SimulationProjet.DoesNotExist:
            simulation = Simulation.objects.get(id=simulation_id)
            simulation_projet = SimulationProjet(
                projet=projet,
                enveloppe_id=simulation.enveloppe_id,
                simulation_id=simulation_id,
            )
        montant = cls.get_initial_montant_from_projet(projet)
        simulation_projet.taux = (
            projet.dossier_ds.annotations_taux
            or ProjetService.compute_taux_from_montant(projet, montant)
        )
        simulation_projet.montant = montant
        simulation_projet.status = cls.get_simulation_projet_status(projet)
        simulation_projet.save()

        return simulation_projet

    @classmethod
    def get_initial_montant_from_projet(cls, projet: Projet):
        if projet.dossier_ds.annotations_montant_accorde:
            return projet.dossier_ds.annotations_montant_accorde
        if projet.dossier_ds.demande_montant:
            return projet.dossier_ds.demande_montant
        return 0

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
            (simulation_projet.projet.assiette_or_cout_total * Decimal(new_taux) / 100)
            if simulation_projet.projet.assiette_or_cout_total
            else 0
        )
        new_montant = round(new_montant, 2)

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()

        if simulation_projet.status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet)

        return simulation_projet

    @classmethod
    def update_montant(cls, simulation_projet, new_montant: float):
        new_taux = ProjetService.compute_taux_from_montant(
            simulation_projet.projet, new_montant
        )

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()

        if simulation_projet.status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet)

        return simulation_projet

    PROJET_STATUS_TO_SIMULATION_PROJET_STATUS = {
        Projet.STATUS_ACCEPTED: SimulationProjet.STATUS_ACCEPTED,
        Projet.STATUS_UNANSWERED: SimulationProjet.STATUS_REFUSED,
        Projet.STATUS_REFUSED: SimulationProjet.STATUS_REFUSED,
        Projet.STATUS_PROCESSING: SimulationProjet.STATUS_PROCESSING,
    }

    # TODO: Tests
    @classmethod
    def get_simulation_projet_status(cls, projet: Projet):
        return cls.PROJET_STATUS_TO_SIMULATION_PROJET_STATUS.get(projet.status)

    @classmethod
    def _accept_a_simulation_projet(cls, simulation_projet: SimulationProjet):
        projet = simulation_projet.projet
        projet.accept(
            montant=simulation_projet.montant, enveloppe=simulation_projet.enveloppe
        )
        projet.save()

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def is_simulation_projet_in_perimetre(
        cls, simulation_projet: SimulationProjet, perimetre: Perimetre
    ):
        projet_arrondissement = simulation_projet.projet.demandeur.arrondissement
        if perimetre.arrondissement is not None:
            return perimetre.arrondissement.pk == projet_arrondissement.pk
        if perimetre.departement is not None:
            return perimetre.departement.pk == projet_arrondissement.departement.pk
        return perimetre.region.pk == projet_arrondissement.departement.region.pk
