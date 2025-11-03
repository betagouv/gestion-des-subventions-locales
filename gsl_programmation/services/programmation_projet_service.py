import logging

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet, Projet

logger = logging.getLogger(__name__)


class ProgrammationProjetService:
    DOTATION_PROJET_STATUS_TO_PROGRAMMATION_STATUS = {
        PROJET_STATUS_ACCEPTED: ProgrammationProjet.STATUS_ACCEPTED,
        PROJET_STATUS_REFUSED: ProgrammationProjet.STATUS_REFUSED,
        PROJET_STATUS_DISMISSED: ProgrammationProjet.STATUS_DISMISSED,
    }

    @classmethod
    def create_or_update_from_dotation_projet(cls, dotation_projet: DotationProjet):
        if dotation_projet.status is None:
            logger.warning(f"Dotation projet {dotation_projet} is missing status")
            return

        if dotation_projet.status not in (
            PROJET_STATUS_ACCEPTED,
            PROJET_STATUS_REFUSED,
            PROJET_STATUS_DISMISSED,
        ):
            ProgrammationProjet.objects.filter(dotation_projet=dotation_projet).delete()
            return

        if dotation_projet.status == PROJET_STATUS_ACCEPTED:
            if (
                getattr(dotation_projet.dossier_ds, "annotations_montant_accorde")
                is None
            ):
                logger.warning(
                    f"Projet accepted {dotation_projet} is missing field annotations_montant_accorde"
                )
                montant = 0
            else:
                montant = dotation_projet.projet.dossier_ds.annotations_montant_accorde
        else:
            montant = 0

        perimetre = cls._get_perimetre_from_dotation(
            dotation_projet.projet, dotation_projet.dotation
        )
        if perimetre is None:
            logger.warning(f"Dotation projet {dotation_projet} is missing perimetre")
            return

        enveloppe, _ = Enveloppe.objects.get_or_create(
            perimetre=perimetre,
            annee=dotation_projet.projet.dossier_ds.ds_date_traitement.year,
            dotation=dotation_projet.dotation,
            defaults={
                "montant": 0,
            },
        )

        ProgrammationProjet.objects.filter(dotation_projet=dotation_projet).exclude(
            enveloppe=enveloppe
        ).delete()

        programmation_projet_status = (
            cls.DOTATION_PROJET_STATUS_TO_PROGRAMMATION_STATUS[dotation_projet.status]
        )

        notified_at = cls._get_notify_datetime_from_dotation_projet(
            dotation_projet.dossier_ds
        )

        programmation_projet, _ = ProgrammationProjet.objects.update_or_create(
            dotation_projet=dotation_projet,
            enveloppe=enveloppe,
            defaults={
                "status": programmation_projet_status,
                "montant": montant,
                "notified_at": notified_at,
            },
        )
        return programmation_projet

    @classmethod
    def _get_perimetre_from_dotation(
        cls, projet: Projet, dotation: str
    ) -> Perimetre | None:
        if dotation == DOTATION_DETR:
            return Perimetre.objects.get(
                departement=projet.perimetre.departement, arrondissement=None
            )

        elif dotation == DOTATION_DSIL:
            return Perimetre.objects.get(
                region=projet.perimetre.departement.region,
                departement=None,
                arrondissement=None,
            )

        return None

    @classmethod
    def _get_notify_datetime_from_dotation_projet(cls, dossier: Dossier):
        """This function is useful because we can have an accepted dotation projet and a "en instruction" dossier due to our process."""
        if dossier.ds_state in (
            Dossier.STATE_ACCEPTE,
            Dossier.STATE_REFUSE,
            Dossier.STATE_SANS_SUITE,
        ):
            return dossier.ds_date_traitement
        return None
