from decimal import Decimal, InvalidOperation

from gsl_projet.constants import DOTATION_DSIL, POSSIBLE_DOTATIONS
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
        detr_avis_commission = (
            None if dotation == DOTATION_DSIL else projet.avis_commission_detr
        )
        assiette = projet.dossier_ds.annotations_assiette or projet.assiette

        dotation_projet, _ = DotationProjet.objects.update_or_create(
            projet=projet,
            dotation=dotation,
            defaults={
                "status": projet.status,
                "assiette": assiette,
                "detr_avis_commission": detr_avis_commission,
            },
        )
        return dotation_projet

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
