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
