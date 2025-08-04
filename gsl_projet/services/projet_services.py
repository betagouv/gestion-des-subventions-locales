import logging
from typing import Any, Literal

from django.db.models import Sum
from django.db.models.query import QuerySet

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    POSSIBLE_DOTATIONS,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.models import Demandeur, DotationProjet, Projet


class ProjetService:
    @classmethod
    def create_or_update_from_ds_dossier(cls, ds_dossier: Dossier):
        try:
            projet = Projet.objects.get(dossier_ds=ds_dossier)
        except Projet.DoesNotExist:
            projet = Projet(
                dossier_ds=ds_dossier,
            )
        projet.address = ds_dossier.projet_adresse
        projet.perimetre = ds_dossier.perimetre
        projet.is_in_qpv = cls.get_is_in_qpv(ds_dossier)
        projet.is_attached_to_a_crte = cls.get_is_attached_to_a_crte(ds_dossier)
        projet.is_budget_vert = cls.get_is_budget_vert(ds_dossier)

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

    @classmethod
    def get_is_in_qpv(cls, ds_dossier: Dossier) -> bool:
        return bool(ds_dossier.annotations_is_qpv)

    @classmethod
    def get_is_attached_to_a_crte(cls, ds_dossier: Dossier) -> bool:
        return bool(ds_dossier.annotations_is_crte)

    @classmethod
    def get_is_budget_vert(cls, ds_dossier: Dossier) -> bool | None:
        if ds_dossier.annotations_is_budget_vert is not None:
            return ds_dossier.annotations_is_budget_vert
        return ds_dossier.environnement_transition_eco

    @classmethod
    def get_dotations_from_field(
        cls,
        projet: Projet,
        field: Literal[
            "annotations_dotation", "demande_dispositif_sollicite"
        ] = "annotations_dotation",
    ) -> list[Any]:
        dotation_annotation = getattr(projet.dossier_ds, field)
        dotations: list[Any] = []

        if dotation_annotation is None:
            logging.warning(f"Projet {projet} is missing annotation dotation")
            return dotations

        if DOTATION_DETR in dotation_annotation:
            dotations.append(DOTATION_DETR)
        if DOTATION_DSIL in dotation_annotation:
            dotations.append(DOTATION_DSIL)

        if not dotations:
            logging.warning(
                f"Projet {projet} annotation dotation {dotation_annotation} is unkown"
            )
        return dotations

    @classmethod
    def update_dotation(cls, projet: Projet, dotations: list[POSSIBLE_DOTATIONS]):
        from gsl_projet.services.dotation_projet_services import DotationProjetService

        if len(dotations) == 0:
            logging.warning(f"Projet {projet} must have at least one dotation")
            return
        if len(dotations) > 2:
            logging.warning(f"Projet {projet} can't have more than two dotations")
            return

        new_dotations = set(dotations) - set(projet.dotations)
        dotation_to_remove = set(projet.dotations) - set(dotations)

        for dotation in new_dotations:
            dotation_projet = DotationProjet.objects.create(
                projet=projet, dotation=dotation, status=PROJET_STATUS_PROCESSING
            )
            DotationProjetService.create_simulation_projets_from_dotation_projet(
                dotation_projet
            )

        DotationProjet.objects.filter(
            projet=projet, dotation__in=dotation_to_remove
        ).delete()
