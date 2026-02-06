import logging

from django.db.models import Sum
from django.db.models.query import QuerySet

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.models import Demandeur, Projet

logger = logging.getLogger(__name__)


class ProjetService:
    @classmethod
    def create_or_update_projet_and_co_from_dossier(cls, ds_dossier_number: str):
        from gsl_projet.services.dotation_projet_services import DotationProjetService

        ds_dossier = Dossier.objects.get(ds_number=ds_dossier_number)
        projet = cls.create_or_update_from_ds_dossier(ds_dossier)
        DotationProjetService.create_or_update_dotation_projet_from_projet(projet)

    @classmethod
    def create_or_update_from_ds_dossier(cls, ds_dossier: Dossier):
        try:
            projet = Projet.objects.get(dossier_ds=ds_dossier)
        except Projet.DoesNotExist:
            projet = Projet(
                dossier_ds=ds_dossier,
            )
        projet.address = ds_dossier.projet_adresse
        projet.perimetre = ds_dossier.get_projet_perimetre()
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

        if ds_dossier.ds_demandeur:
            projet.demandeur, _ = Demandeur.objects.get_or_create(
                siret=ds_dossier.ds_demandeur.siret,
                defaults={
                    "name": ds_dossier.ds_demandeur.raison_sociale,
                    "address": ds_dossier.ds_demandeur.address,
                },
            )

        projet.save()
        return projet

    @classmethod
    def get_total_cost(cls, projet_qs: QuerySet):
        return projet_qs.aggregate(total=Sum("dossier_ds__finance_cout_total"))["total"]

    @classmethod
    def get_total_amount_asked(cls, projet_qs: QuerySet):
        return projet_qs.aggregate(Sum("dossier_ds__demande_montant"))[
            "dossier_ds__demande_montant__sum"
        ]

    @classmethod
    def get_total_amount_granted(cls, projet_qs: QuerySet):
        from gsl_programmation.models import ProgrammationProjet

        projet_ids = projet_qs.values_list("pk", flat=True)
        return ProgrammationProjet.objects.filter(
            dotation_projet__projet__in=projet_ids,
            status=ProgrammationProjet.STATUS_ACCEPTED,
        ).aggregate(total=Sum("montant"))["total"]

    # Private

    @classmethod
    def _get_boolean_value(cls, ds_dossier: Dossier, annotation_name: str) -> bool:
        return bool(getattr(ds_dossier, annotation_name))
