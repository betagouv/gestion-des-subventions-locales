from gsl_projet.constants import DOTATION_DSIL, POSSIBLE_DOTATIONS
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.services.projet_services import ProjetService


class DotationProjetService:
    @classmethod
    def create_or_update_dotation_projet_from_projet(cls, projet: Projet):
        dotations = ProjetService.get_dotations_from_field(
            projet, "annotations_dotation"
        )
        if not dotations:
            dotations = ProjetService.get_dotations_from_field(
                projet, "demande_dispositif_sollicite"
            )
        for dotation in dotations:
            cls.create_or_update_dotation_projet(projet, dotation)

        DotationProjet.objects.filter(projet=projet).exclude(
            dotation__in=dotations
        ).delete()

    @classmethod
    def create_or_update_dotation_projet(
        cls, projet: Projet, dotation: POSSIBLE_DOTATIONS
    ):
        avis_commission_detr = (
            None if dotation == DOTATION_DSIL else projet.avis_commission_detr
        )

        dotation_projet, _ = DotationProjet.objects.update_or_create(
            projet=projet,
            dotation=dotation,
            defaults={
                "status": projet.status,
                "assiette": projet.assiette,
                "avis_commission_detr": avis_commission_detr,
            },
        )
        return dotation_projet
