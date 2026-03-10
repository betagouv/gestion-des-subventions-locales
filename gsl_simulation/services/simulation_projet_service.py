import logging
from decimal import Decimal

from gsl_programmation.models import ProgrammationProjet
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_simulation.models import Simulation, SimulationProjet

logger = logging.getLogger(__name__)


class SimulationProjetService:
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
            simulation=simulation,
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

        if dotation_projet.dotation == DOTATION_DETR:
            dossier_montant_annotations = dossier.annotations_montant_accorde_detr
        elif dotation_projet.dotation == DOTATION_DSIL:
            dossier_montant_annotations = dossier.annotations_montant_accorde_dsil

        if dossier_montant_annotations:
            return cls._select_minimum_between_value_and_assiette_or_cout_total(
                dossier_montant_annotations,
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
            logger.warning(
                f"Le projet de dotation {dotation_projet.dotation} (id: {dotation_projet.pk}) n'a ni assiette ni coût total."
            )
            return value

        if value and value > dotation_projet.assiette_or_cout_total:
            logger.warning(
                f"Le projet de dotation {dotation_projet.dotation} (id: {dotation_projet.pk}) a une assiette plus petite que {value_label}."
            )

        return min(
            value,
            dotation_projet.assiette_or_cout_total,
        )

    PROJET_STATUS_TO_SIMULATION_PROJET_STATUS = {
        PROJET_STATUS_ACCEPTED: SimulationProjet.STATUS_ACCEPTED,
        PROJET_STATUS_DISMISSED: SimulationProjet.STATUS_DISMISSED,
        PROJET_STATUS_REFUSED: SimulationProjet.STATUS_REFUSED,
        PROJET_STATUS_PROCESSING: SimulationProjet.STATUS_PROCESSING,
    }

    @classmethod
    def get_simulation_projet_status(cls, dotation_projet: DotationProjet):
        return cls.PROJET_STATUS_TO_SIMULATION_PROJET_STATUS.get(dotation_projet.status)
