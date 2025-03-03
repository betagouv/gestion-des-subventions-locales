import logging

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import Enveloppe, ProgrammationProjet
from gsl_projet.models import Projet


class ProgrammationProjetService:
    PROJET_MANDATORY_FIELDS_TO_CREATE_OR_UPDATE_PROGRAMMATION_PROJET = [
        "dossier_ds",
        "annotations_montant_accorde",
        "annotations_taux",
        "annotations_dotation",
        "annotations_assiette",
    ]

    @classmethod
    def create_or_update_from_projet(cls, projet: Projet):
        if projet.status is None:
            logging.error(f"Projet {projet} is missing status")
            return

        if projet.status not in (Projet.STATUS_ACCEPTED, Projet.STATUS_REFUSED):
            ProgrammationProjet.objects.filter(projet=projet).delete()
            return

        dotation = cls.compute_from_annotation(projet)

        if projet.status == Projet.STATUS_ACCEPTED:
            for field in (
                "annotations_montant_accorde",
                "annotations_taux",
                "annotations_assiette",
            ):
                if getattr(projet.dossier_ds, field) is None:
                    logging.error(f"Projet accepted {projet} is missing field {field}")
                    return

        perimetre = cls.get_perimetre_from_dotation(projet, dotation)
        if perimetre is None:
            logging.error(f"Projet {projet} is missing perimetre")
            return

        enveloppe = Enveloppe.objects.get(
            perimetre=perimetre,
            annee=projet.dossier_ds.ds_date_traitement.year,
            type=dotation,
        )

        ProgrammationProjet.objects.filter(projet=projet).exclude(
            enveloppe=enveloppe
        ).delete()

        montant = (
            projet.dossier_ds.annotations_montant_accorde
            if projet.status == Projet.STATUS_ACCEPTED
            else 0
        )
        taux = (
            projet.dossier_ds.annotations_taux
            if projet.status == Projet.STATUS_ACCEPTED
            else 0
        )
        programmation_projet_status = (
            ProgrammationProjet.STATUS_ACCEPTED
            if projet.status == Projet.STATUS_ACCEPTED
            else ProgrammationProjet.STATUS_REFUSED
        )

        programmation_projet, _ = ProgrammationProjet.objects.update_or_create(
            projet=projet,
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
        if dotation == Dossier.DOTATION_DETR:
            return Perimetre.objects.get(
                departement=projet.perimetre.departement, arrondissement=None
            )

        elif dotation == Dossier.DOTATION_DSIL:
            return Perimetre.objects.get(
                region=projet.perimetre.departement.region,
                departement=None,
                arrondissement=None,
            )

        return None

    @classmethod
    def compute_from_annotation(cls, projet):
        dotation_annotation = projet.dossier_ds.annotations_dotation
        if dotation_annotation is None:
            logging.error(f"Projet {projet} is missing annotation dotation")
            raise ValueError(f"Projet {projet} is missing annotation dotation")

        if "DETR" in dotation_annotation and "DSIL" in dotation_annotation:
            raise ValueError(
                f"Projet {projet} annotation dotation contains both DETR and DSIL"
            )

        if "DETR" in dotation_annotation:
            return Dossier.DOTATION_DETR

        if "DSIL" in dotation_annotation:
            return Dossier.DOTATION_DSIL

        raise ValueError(
            f"Projet {projet} annotation dotation {dotation_annotation} is unkown"
        )
