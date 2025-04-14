from decimal import Decimal

from gsl_core.models import Perimetre
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.services.projet_services import ProjetService
from gsl_simulation.models import Simulation, SimulationProjet


class SimulationProjetService:
    @classmethod
    def update_simulation_projets_from_dotation_projet(
        cls, dotation_projet: DotationProjet
    ):
        simulation_projets = SimulationProjet.objects.filter(
            dotation_projet=dotation_projet
        ).select_related("simulation")

        for simulation_projet in simulation_projets:
            cls.create_or_update_simulation_projet_from_dotation_projet(
                dotation_projet, simulation_projet.simulation
            )

    @classmethod
    def create_or_update_simulation_projet_from_dotation_projet(
        cls, dotation_projet: DotationProjet, simulation: Simulation
    ):
        """
        Create or update a SimulationProjet from a Dotation Projet and a Simulation.
        """
        montant = cls.get_initial_montant_from_projet(dotation_projet.projet)
        simulation_projet, _ = SimulationProjet.objects.update_or_create(
            projet=dotation_projet.projet,  # TODO pr_dotation remove it
            dotation_projet=dotation_projet,
            simulation_id=simulation.id,
            defaults={
                "montant": montant,
                "taux": (
                    dotation_projet.projet.dossier_ds.annotations_taux
                    or ProjetService.compute_taux_from_montant(
                        dotation_projet.projet, montant
                    )
                ),
                "status": cls.get_simulation_projet_status(dotation_projet),
            },
        )

        return simulation_projet

    @classmethod
    def get_initial_montant_from_projet(cls, projet: Projet) -> Decimal:
        if projet.dossier_ds.annotations_montant_accorde:
            return projet.dossier_ds.annotations_montant_accorde
        if projet.dossier_ds.demande_montant:
            return projet.dossier_ds.demande_montant
        return Decimal(0)

    @classmethod
    def update_status(cls, simulation_projet: SimulationProjet, new_status: str):
        if new_status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet)

        if new_status == SimulationProjet.STATUS_REFUSED:
            return cls._refuse_a_simulation_projet(simulation_projet)

        if new_status == SimulationProjet.STATUS_DISMISSED:
            return cls._dismiss_a_simulation_projet(simulation_projet)

        if (
            new_status == SimulationProjet.STATUS_PROCESSING
            and simulation_projet.status
            in (
                SimulationProjet.STATUS_ACCEPTED,
                SimulationProjet.STATUS_REFUSED,
                SimulationProjet.STATUS_DISMISSED,
            )
        ):
            return cls._set_back_to_processing(simulation_projet)

        if (
            new_status == SimulationProjet.STATUS_PROVISOIRE
            and simulation_projet.status
            in (
                SimulationProjet.STATUS_ACCEPTED,
                SimulationProjet.STATUS_REFUSED,
                SimulationProjet.STATUS_DISMISSED,
            )
        ):
            cls._set_back_to_processing(simulation_projet)

        simulation_projet.status = new_status
        simulation_projet.save()
        return simulation_projet

    # TODO pr_dotation update test
    @classmethod
    def update_taux(cls, simulation_projet: SimulationProjet, new_taux: float):
        assiette = simulation_projet.dotation_projet.assiette_or_cout_total
        new_montant = (assiette * Decimal(new_taux) / 100) if assiette else 0
        new_montant = round(new_montant, 2)

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()

        if simulation_projet.status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet)

        return simulation_projet

    @classmethod
    def update_montant(cls, simulation_projet: SimulationProjet, new_montant: float):
        new_taux = DotationProjetService.compute_taux_from_montant(
            simulation_projet.dotation_projet, new_montant
        )

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()

        if simulation_projet.status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet)

        return simulation_projet

    PROJET_STATUS_TO_SIMULATION_PROJET_STATUS = {
        DotationProjet.STATUS_ACCEPTED: SimulationProjet.STATUS_ACCEPTED,
        DotationProjet.STATUS_DISMISSED: SimulationProjet.STATUS_DISMISSED,
        DotationProjet.STATUS_REFUSED: SimulationProjet.STATUS_REFUSED,
        DotationProjet.STATUS_PROCESSING: SimulationProjet.STATUS_PROCESSING,
    }

    @classmethod
    def get_simulation_projet_status(cls, dotation_projet: DotationProjet):
        return cls.PROJET_STATUS_TO_SIMULATION_PROJET_STATUS.get(dotation_projet.status)

    @classmethod
    def _accept_a_simulation_projet(cls, simulation_projet: SimulationProjet):
        dotation_projet = simulation_projet.dotation_projet
        dotation_projet.accept(
            montant=simulation_projet.montant, enveloppe=simulation_projet.enveloppe
        )
        dotation_projet.save()

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def _refuse_a_simulation_projet(cls, simulation_projet: SimulationProjet):
        dotation_projet = simulation_projet.dotation_projet
        dotation_projet.refuse(enveloppe=simulation_projet.enveloppe)
        dotation_projet.save()

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def _dismiss_a_simulation_projet(cls, simulation_projet: SimulationProjet):
        projet = simulation_projet.projet
        projet.dismiss()
        projet.save()

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def _set_back_to_processing(cls, simulation_projet: SimulationProjet):
        projet = simulation_projet.projet
        projet.set_back_status_to_processing()
        projet.save()

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def is_simulation_projet_in_perimetre(
        cls, simulation_projet: SimulationProjet, perimetre: Perimetre
    ):
        simulation_projet_perimetre = simulation_projet.projet.perimetre
        if perimetre.arrondissement is not None:
            return (
                perimetre.arrondissement_id
                == simulation_projet_perimetre.arrondissement_id
            )
        if perimetre.departement is not None:
            return (
                perimetre.departement_id == simulation_projet_perimetre.departement_id
            )
        return perimetre.region_id == simulation_projet_perimetre.departement.region_id
