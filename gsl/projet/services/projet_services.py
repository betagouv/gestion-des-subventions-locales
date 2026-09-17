import logging

from gsl.historique.utils import create_projet_actions_from_dossier_traitements
from gsl_demarches_simplifiees.models import Dossier

from ..models import Projet

logger = logging.getLogger(__name__)


class ProjetService:
    @classmethod
    def create_or_update_projet_and_co_from_dossier(cls, ds_dossier_number: str):
        from .enveloppe_projet_services import EnveloppeProjetService

        ds_dossier = Dossier.objects.get(ds_number=ds_dossier_number)
        projet = cls.create_or_update_from_ds_dossier(ds_dossier)
        EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet(projet)

    @classmethod
    def create_or_update_from_ds_dossier(cls, ds_dossier: Dossier):
        try:
            projet = Projet.objects.get(dossier_ds=ds_dossier)
        except Projet.DoesNotExist:
            projet = Projet(
                dossier_ds=ds_dossier,
            )
        projet.address = ds_dossier.projet_adresse
        projet.is_in_qpv = cls._get_boolean_value(ds_dossier, "annotations_is_qpv")
        projet.is_attached_to_a_crte = cls._get_boolean_value(
            ds_dossier, "annotations_is_crte"
        )
        projet.is_budget_vert = cls._get_boolean_value(
            ds_dossier, "annotations_is_budget_vert"
        )
        projet.is_frr = cls._get_boolean_value(ds_dossier, "annotations_is_frr")
        projet.is_acv = cls._get_boolean_value(ds_dossier, "annotations_is_acv")
        projet.is_pvd = cls._get_boolean_value(ds_dossier, "annotations_is_pvd")
        projet.is_va = cls._get_boolean_value(ds_dossier, "annotations_is_va")
        projet.is_autre_zonage_local = cls._get_boolean_value(
            ds_dossier, "annotations_is_autre_zonage_local"
        )
        projet.autre_zonage_local = ds_dossier.annotations_autre_zonage_local
        projet.is_contrat_local = cls._get_boolean_value(
            ds_dossier, "annotations_is_contrat_local"
        )
        projet.contrat_local = ds_dossier.annotations_contrat_local
        if ds_dossier.is_treated:
            projet.notified_at = ds_dossier.ds_date_traitement
        else:
            projet.notified_at = None

        projet.save()

        create_projet_actions_from_dossier_traitements(projet)
        return projet

    # Private

    @classmethod
    def _get_boolean_value(cls, ds_dossier: Dossier, annotation_name: str) -> bool:
        return bool(getattr(ds_dossier, annotation_name))
