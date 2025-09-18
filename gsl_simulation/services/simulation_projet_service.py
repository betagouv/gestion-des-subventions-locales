import logging
from decimal import Decimal

from gsl_core.models import Collegue
from gsl_demarches_simplifiees.exceptions import DsServiceException
from gsl_demarches_simplifiees.mixins import build_error_message, process_projet_update
from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_projet.services.dotation_projet_services import DotationProjetService
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
        simulation_projet_status = cls.get_simulation_projet_status(dotation_projet)
        montant = cls.get_initial_montant_from_dotation_projet(
            dotation_projet, simulation_projet_status
        )
        simulation_projet, _ = SimulationProjet.objects.update_or_create(
            dotation_projet=dotation_projet,
            simulation_id=simulation.id,
            defaults={
                "montant": montant,
                "status": simulation_projet_status,
            },
        )

        return simulation_projet

    @classmethod
    def get_initial_montant_from_dotation_projet(
        cls, dotation_projet: DotationProjet, status: str
    ) -> Decimal:
        if status in (
            SimulationProjet.STATUS_DISMISSED,
            SimulationProjet.STATUS_REFUSED,
        ):
            return Decimal(0)

        try:
            return dotation_projet.programmation_projet.montant
        except ProgrammationProjet.DoesNotExist:
            pass

        dossier = dotation_projet.projet.dossier_ds

        if dossier.annotations_montant_accorde:
            return cls._select_minimum_between_value_and_assiette_or_cout_total(
                dossier.annotations_montant_accorde,
                dotation_projet,
                "le montant accordé issu des annotations",
            )

        if dossier.demande_montant:
            return cls._select_minimum_between_value_and_assiette_or_cout_total(
                dossier.demande_montant,
                dotation_projet,
                "le montant demandé",
            )

        return Decimal(0)

    @classmethod
    def _select_minimum_between_value_and_assiette_or_cout_total(
        cls, value: Decimal, dotation_projet: DotationProjet, value_label: str
    ):
        if dotation_projet.assiette_or_cout_total is None:
            logging.warning(
                f"Le projet de dotation {dotation_projet.dotation} (id: {dotation_projet.pk}) n'a ni assiette ni coût total."
            )
            return value

        if value and value > dotation_projet.assiette_or_cout_total:
            logging.warning(
                f"Le projet de dotation {dotation_projet.dotation} (id: {dotation_projet.pk}) a une assiette plus petite que {value_label}."
            )

        return min(
            value,
            dotation_projet.assiette_or_cout_total,
        )

    @classmethod
    def update_status(
        cls, simulation_projet: SimulationProjet, new_status: str, user: Collegue
    ):
        if new_status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet, user)

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

        if new_status in (
            SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
            SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
        ) and simulation_projet.status in (
            SimulationProjet.STATUS_ACCEPTED,
            SimulationProjet.STATUS_REFUSED,
            SimulationProjet.STATUS_DISMISSED,
        ):
            cls._set_back_to_processing(simulation_projet)

        simulation_projet.status = new_status
        simulation_projet.save()
        return simulation_projet

    @classmethod
    def update_taux(
        cls, simulation_projet: SimulationProjet, new_taux: float, user: Collegue
    ):
        new_montant = DotationProjetService.compute_montant_from_taux(
            simulation_projet.dotation_projet, new_taux
        )
        simulation_projet.montant = new_montant
        simulation_projet.save()

        if simulation_projet.status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet, user)

        return simulation_projet

    @classmethod
    def update_montant(
        cls, simulation_projet: SimulationProjet, new_montant: float, user: Collegue
    ):
        simulation_projet.montant = new_montant
        simulation_projet.save()

        if simulation_projet.status == SimulationProjet.STATUS_ACCEPTED:
            return cls._accept_a_simulation_projet(simulation_projet, user)

        return simulation_projet

    PROJET_STATUS_TO_SIMULATION_PROJET_STATUS = {
        PROJET_STATUS_ACCEPTED: SimulationProjet.STATUS_ACCEPTED,
        PROJET_STATUS_DISMISSED: SimulationProjet.STATUS_DISMISSED,
        PROJET_STATUS_REFUSED: SimulationProjet.STATUS_REFUSED,
        PROJET_STATUS_PROCESSING: SimulationProjet.STATUS_PROCESSING,
    }

    @classmethod
    def get_simulation_projet_status(cls, dotation_projet: DotationProjet):
        return cls.PROJET_STATUS_TO_SIMULATION_PROJET_STATUS.get(dotation_projet.status)

    # Private

    @classmethod
    def _accept_a_simulation_projet(
        cls, simulation_projet: SimulationProjet, user: Collegue
    ):
        dotation_projet = simulation_projet.dotation_projet

        dotation_projet.accept(
            montant=simulation_projet.montant, enveloppe=simulation_projet.enveloppe
        )
        dotation_projet.save()

        cls._update_ds_montant_and_taux(
            dossier=dotation_projet.projet.dossier_ds,
            montant=simulation_projet.montant,
            taux=simulation_projet.taux,
            user=user,
        )

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
        dotation_projet = simulation_projet.dotation_projet
        dotation_projet.dismiss()
        dotation_projet.save()

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def _set_back_to_processing(cls, simulation_projet: SimulationProjet):
        dotation_projet = simulation_projet.dotation_projet
        dotation_projet.set_back_status_to_processing()
        dotation_projet.save()

        updated_simulation_projet = SimulationProjet.objects.get(
            pk=simulation_projet.pk
        )
        return updated_simulation_projet

    @classmethod
    def _update_ds_montant_and_taux(
        cls, dossier: Dossier, montant: float, taux: float, user: Collegue
    ) -> None:
        data = {
            "montant": montant,
            "taux": taux,
        }
        errors, blocking = process_projet_update(
            data, dossier, ["montant", "taux"], user
        )

        if blocking:
            raise DsServiceException(
                "Une erreur est survenue lors de la mise à jour des informations "
                f"sur Démarches Simplifiées. {errors['all']}"
            )

        error_msg = None

        if not errors:
            return

        fields_msg = build_error_message(errors)
        error_msg = (
            "Une erreur est survenue lors de la mise à jour de certaines "
            "informations sur Démarches Simplifiées "
            f"({fields_msg}). Ces modifications n'ont pas été enregistrées."
        )
        raise DsServiceException(error_msg)
