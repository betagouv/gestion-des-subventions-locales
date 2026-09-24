import logging
from decimal import Decimal

from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from gsl.projet.models import EnveloppeProjet

from ..models import Simulation, SimulationProjet

logger = logging.getLogger(__name__)


class SimulationProjetService:
    @classmethod
    def create_or_update_simulation_projet_from_enveloppe_projet(
        cls, enveloppe_projet: EnveloppeProjet, simulation: Simulation
    ):
        """
        Create or update a SimulationProjet from a Enveloppe Projet and a Simulation.
        """
        simulation_projet_status = cls.get_simulation_projet_status(enveloppe_projet)
        montant = cls.get_initial_montant_from_enveloppe_projet(
            enveloppe_projet, simulation_projet_status
        )
        simulation_projet, _ = SimulationProjet.objects.update_or_create(
            enveloppe_projet=enveloppe_projet,
            simulation=simulation,
            defaults={
                "montant": montant,
                "status": simulation_projet_status,
            },
        )

        return simulation_projet

    @classmethod
    def get_initial_montant_from_enveloppe_projet(
        cls, enveloppe_projet: EnveloppeProjet, status: str
    ) -> Decimal:
        if status in (
            SimulationProjet.STATUS_DISMISSED,
            SimulationProjet.STATUS_REFUSED,
        ):
            return Decimal(0)

        if enveloppe_projet.montant is not None:
            return enveloppe_projet.montant

        dossier = enveloppe_projet.projet.dossier_ds

        if enveloppe_projet.dotation == DOTATION_DETR:
            dossier_montant_annotations = dossier.annotations_montant_accorde_detr
        elif enveloppe_projet.dotation == DOTATION_DSIL:
            dossier_montant_annotations = dossier.annotations_montant_accorde_dsil

        if dossier_montant_annotations:
            return cls._select_minimum_between_value_and_assiette_or_cout_total(
                dossier_montant_annotations,
                enveloppe_projet,
                "le montant accordé issu des annotations",
            )

        if dossier.demande_montant:
            return cls._select_minimum_between_value_and_assiette_or_cout_total(
                dossier.demande_montant,
                enveloppe_projet,
                "le montant demandé",
            )

        return Decimal(0)

    @classmethod
    def _select_minimum_between_value_and_assiette_or_cout_total(
        cls, value: Decimal, enveloppe_projet: EnveloppeProjet, value_label: str
    ):
        if enveloppe_projet.assiette_or_cout_total is None:
            logger.warning(
                f"Le projet de dotation {enveloppe_projet.dotation} (id: {enveloppe_projet.pk}) n'a ni assiette ni coût total."
            )
            return value

        if value and value > enveloppe_projet.assiette_or_cout_total:
            logger.warning(
                f"Le projet de dotation {enveloppe_projet.dotation} (id: {enveloppe_projet.pk}) a une assiette plus petite que {value_label}."
            )

        return min(
            value,
            enveloppe_projet.assiette_or_cout_total,
        )

    PROJET_STATUS_TO_SIMULATION_PROJET_STATUS = {
        ProjetStatus.ACCEPTED: SimulationProjet.STATUS_ACCEPTED,
        ProjetStatus.DISMISSED: SimulationProjet.STATUS_DISMISSED,
        ProjetStatus.REFUSED: SimulationProjet.STATUS_REFUSED,
        ProjetStatus.PROCESSING: SimulationProjet.STATUS_PROCESSING,
    }

    @classmethod
    def get_simulation_projet_status(cls, enveloppe_projet: EnveloppeProjet):
        return cls.PROJET_STATUS_TO_SIMULATION_PROJET_STATUS.get(
            enveloppe_projet.status
        )
