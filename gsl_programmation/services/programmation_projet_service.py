import logging

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet, Projet


class ProgrammationProjetService:
    PROJET_MANDATORY_FIELDS_TO_CREATE_OR_UPDATE_PROGRAMMATION_PROJET = [
        "dossier_ds",
        "annotations_montant_accorde",
        "annotations_taux",
        "annotations_dotation",
        "annotations_assiette",
    ]

    @classmethod
    def create_or_update_from_dotation_projet(cls, dotation_projet: DotationProjet):
        if dotation_projet.status is None:
            logging.error(f"Dotation projet {dotation_projet} is missing status")
            return

        if dotation_projet.status not in (
            PROJET_STATUS_ACCEPTED,
            PROJET_STATUS_REFUSED,
        ):
            ProgrammationProjet.objects.filter(dotation_projet=dotation_projet).delete()
            return

        if dotation_projet.status == PROJET_STATUS_ACCEPTED:
            for field in (
                "annotations_montant_accorde",
                "annotations_taux",
                "annotations_assiette",
            ):
                # TODO pr_dotation add a property dossier_ds to dotation_projet ?
                if getattr(dotation_projet.projet.dossier_ds, field) is None:
                    logging.error(
                        f"Projet accepted {dotation_projet} is missing field {field}"
                    )
                    return

        perimetre = cls.get_perimetre_from_dotation(
            dotation_projet.projet, dotation_projet.dotation
        )
        if perimetre is None:
            logging.error(f"Dotation projet {dotation_projet} is missing perimetre")
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

        montant = (
            dotation_projet.projet.dossier_ds.annotations_montant_accorde
            if dotation_projet.status == PROJET_STATUS_ACCEPTED
            else 0
        )
        taux = (
            dotation_projet.projet.dossier_ds.annotations_taux
            if dotation_projet.status == PROJET_STATUS_ACCEPTED
            else 0
        )
        programmation_projet_status = (
            ProgrammationProjet.STATUS_ACCEPTED
            if dotation_projet.status == PROJET_STATUS_ACCEPTED
            else ProgrammationProjet.STATUS_REFUSED
        )

        programmation_projet, _ = ProgrammationProjet.objects.update_or_create(
            dotation_projet=dotation_projet,
            enveloppe=enveloppe,
            defaults={
                "status": programmation_projet_status,
                "montant": montant,
                "taux": taux,
            },
        )
        return programmation_projet

    @classmethod
    def get_perimetre_from_dotation(
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
