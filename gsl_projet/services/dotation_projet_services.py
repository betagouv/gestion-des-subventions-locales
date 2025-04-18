from decimal import Decimal, InvalidOperation

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.constants import (
    DOTATION_DETR,
    POSSIBLE_DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.projet_services import ProjetService


class DotationProjetService:
    @classmethod
    def create_or_update_dotation_projet_from_projet(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotations = ProjetService.get_dotations_from_field(
            projet, "annotations_dotation"
        )
        if not dotations:
            dotations = ProjetService.get_dotations_from_field(
                projet, "demande_dispositif_sollicite"
            )

        dotation_projets = []
        for dotation in dotations:
            dotation_projets.append(
                cls.create_or_update_dotation_projet(projet, dotation)
            )
        return dotation_projets

    @classmethod
    def create_or_update_dotation_projet(
        cls, projet: Projet, dotation: POSSIBLE_DOTATIONS
    ):
        detr_avis_commission = cls.get_detr_avis_commission(dotation, projet.dossier_ds)
        assiette = projet.dossier_ds.annotations_assiette

        dotation_projet, _ = DotationProjet.objects.update_or_create(
            projet=projet,
            dotation=dotation,
            defaults={
                "status": cls.get_dotation_projet_status_from_dossier(
                    projet.dossier_ds
                ),
                "assiette": assiette,
                "detr_avis_commission": detr_avis_commission,
            },
        )
        return dotation_projet

    DOSSIER_DS_STATUS_TO_DOTATION_PROJET_STATUS = {
        Dossier.STATE_ACCEPTE: PROJET_STATUS_ACCEPTED,
        Dossier.STATE_EN_CONSTRUCTION: PROJET_STATUS_PROCESSING,
        Dossier.STATE_EN_INSTRUCTION: PROJET_STATUS_PROCESSING,
        Dossier.STATE_REFUSE: PROJET_STATUS_REFUSED,
        Dossier.STATE_SANS_SUITE: PROJET_STATUS_DISMISSED,
    }

    @classmethod
    def get_dotation_projet_status_from_dossier(cls, ds_dossier: Dossier):
        return cls.DOSSIER_DS_STATUS_TO_DOTATION_PROJET_STATUS.get(ds_dossier.ds_state)

    @classmethod
    def get_detr_avis_commission(cls, dotation: str, ds_dossier: Dossier):
        if dotation == DOTATION_DETR and ds_dossier.ds_state == Dossier.STATE_ACCEPTE:
            return True

        return None

    @classmethod
    def compute_taux_from_montant(
        cls, dotation_projet: DotationProjet, new_montant: float | Decimal
    ) -> Decimal:
        try:
            new_taux = round(
                (Decimal(new_montant) / Decimal(dotation_projet.assiette_or_cout_total))
                * 100,
                2,
            )
            return max(min(new_taux, Decimal(100)), Decimal(0))
        except TypeError:
            return Decimal(0)
        except ZeroDivisionError:
            return Decimal(0)
        except InvalidOperation:
            return Decimal(0)

    @classmethod
    def validate_montant(
        cls, montant: float | Decimal, dotation_projet: DotationProjet
    ) -> None:
        if (
            type(montant) not in [float, Decimal, int]
            or montant < 0
            or dotation_projet.assiette_or_cout_total is None
            or montant > dotation_projet.assiette_or_cout_total
        ):
            raise ValueError(
                f"Montant {montant} must be greatear or equal to 0 and less than or equal to {dotation_projet.assiette_or_cout_total}"
            )

    @classmethod
    def validate_taux(cls, taux: float | Decimal) -> None:
        if type(taux) not in [float, Decimal, int] or taux < 0 or taux > 100:
            raise ValueError(f"Taux {taux} must be between 0 and 100")
