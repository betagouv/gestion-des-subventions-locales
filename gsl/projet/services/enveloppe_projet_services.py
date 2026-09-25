import logging
from datetime import date
from typing import Any, Literal

from django.db import transaction

from gsl.core.models import Perimetre
from gsl.historique.models import ProjetAction
from gsl.programmation.models import Enveloppe
from gsl.simulation.models import Simulation, SimulationProjet
from gsl_demarches_simplifiees.models import Dossier

from ..constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    POSSIBLE_DOTATIONS,
    ProjetStatus,
)
from ..models import EnveloppeProjet, Projet

logger = logging.getLogger(__name__)


class EnveloppeProjetService:
    @classmethod
    def create_or_update_enveloppe_projet_from_projet(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        # check for initialisation
        if projet.enveloppeprojet_set.count() == 0:
            enveloppe_projets = cls._initialize_enveloppe_projets_from_projet(projet)

        else:
            if cls._should_dotations_be_updated_from_dn_construction_dossier(projet):
                cls._remove_or_add_dotations_from_dossier_ds(projet)
            # check for updates
            enveloppe_projets = cls._update_enveloppe_projets_from_projet(projet)

        cls._add_enveloppe_projets_to_all_concerned_simulations(enveloppe_projets)
        cls._remove_enveloppe_projets_from_unconcerned_simulations(enveloppe_projets)
        return enveloppe_projets

    @classmethod
    def create_simulation_projets_from_enveloppe_projet(
        cls,
        enveloppe_projet: EnveloppeProjet,
    ):
        from gsl.simulation.services.simulation_projet_service import (
            SimulationProjetService,
        )

        projet_perimetre = enveloppe_projet.projet.perimetre
        perimetres_containing_this_projet_perimetre = list(projet_perimetre.ancestors())
        perimetres_containing_this_projet_perimetre.append(projet_perimetre)
        enveloppes = Enveloppe.objects.filter(
            dotation=enveloppe_projet.dotation,
            perimetre__in=perimetres_containing_this_projet_perimetre,
            annee__gte=date.today().year,
        )
        simulations = Simulation.objects.filter(enveloppe__in=enveloppes)
        for simulation in simulations:
            SimulationProjetService.create_or_update_simulation_projet_from_enveloppe_projet(
                enveloppe_projet, simulation
            )

    # private

    ## -------------------------- Initialize Enveloppe Projets --------------------------

    @classmethod
    @transaction.atomic
    def _initialize_enveloppe_projets_from_projet(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        dossier_status = projet.dossier_ds.ds_state
        if dossier_status == Dossier.STATE_ACCEPTE:
            return cls._initialize_enveloppe_projets_from_projet_accepted(projet)
        elif dossier_status == Dossier.STATE_REFUSE:
            return cls._initialize_enveloppe_projets_from_projet_refused(projet)
        elif dossier_status == Dossier.STATE_SANS_SUITE:
            return cls._initialize_enveloppe_projets_from_projet_sans_suite(projet)
        elif dossier_status in [
            Dossier.STATE_EN_CONSTRUCTION,
            Dossier.STATE_EN_INSTRUCTION,
        ]:
            return cls._initialize_enveloppe_projets_from_projet_en_construction_or_instruction(
                projet
            )

        raise ValueError(f"Invalid dossier status: {dossier_status}")

    @classmethod
    def _initialize_enveloppe_projets_from_projet_accepted(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        dotations = cls._get_dotations_from_field(
            projet,
            "annotations_dotation",
            log_message_if_missing="No dotations found in annotations_dotation for accepted dossier during initialisation",
        )

        if not dotations:
            dotations = cls._get_dotations_from_field(
                projet, "demande_dispositif_sollicite"
            )

        enveloppe_projets = []
        for dotation in dotations:
            enveloppe_projet = cls._create_enveloppe_projet(projet, dotation)
            enveloppe = cls._get_root_enveloppe_from_enveloppe_projet(enveloppe_projet)
            montant = cls._get_montant_from_dossier(projet.dossier_ds, dotation)
            enveloppe_projet.accept_without_ds_update(
                montant=montant, enveloppe=enveloppe
            )
            enveloppe_projet.save()
            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    @classmethod
    def _initialize_enveloppe_projets_from_projet_refused(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        dotations = cls._get_dotations_from_field(
            projet, "demande_dispositif_sollicite"
        )
        enveloppe_projets = []
        for dotation in dotations:
            enveloppe_projet = cls._create_enveloppe_projet(projet, dotation)
            enveloppe = cls._get_root_enveloppe_from_enveloppe_projet(
                enveloppe_projet, allow_next_year=True
            )
            enveloppe_projet.refuse(enveloppe=enveloppe)
            enveloppe_projet.save()
            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    @classmethod
    def _initialize_enveloppe_projets_from_projet_sans_suite(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        dotations = cls._get_dotations_from_field(
            projet, "demande_dispositif_sollicite"
        )
        enveloppe_projets = []
        for dotation in dotations:
            enveloppe_projet = cls._create_enveloppe_projet(projet, dotation)
            enveloppe = cls._get_root_enveloppe_from_enveloppe_projet(
                enveloppe_projet, allow_next_year=True
            )
            enveloppe_projet.dismiss(enveloppe=enveloppe)
            enveloppe_projet.save()
            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    @classmethod
    def _initialize_enveloppe_projets_from_projet_en_construction_or_instruction(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        dotations = cls._get_dotations_from_field(
            projet, "demande_dispositif_sollicite"
        )
        enveloppe_projets = []
        for dotation in dotations:
            enveloppe_projet = cls._create_enveloppe_projet(projet, dotation)
            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    @classmethod
    def _create_enveloppe_projet(
        cls, projet: Projet, dotation: POSSIBLE_DOTATIONS
    ) -> EnveloppeProjet:
        detr_avis_commission = cls._get_detr_avis_commission(
            dotation, projet.dossier_ds
        )
        assiette = cls._get_assiette_from_annotations(projet.dossier_ds, dotation)
        kwargs = {
            "projet": projet,
            "dotation": dotation,
            "detr_avis_commission": detr_avis_commission,
        }
        if assiette is not None:
            kwargs["assiette"] = assiette
        return EnveloppeProjet.objects.create(**kwargs)

    ## -------------------------- Update Enveloppe Projets --------------------------

    @classmethod
    @transaction.atomic
    def _update_enveloppe_projets_from_projet(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        cls._update_assiette_from_dossier(projet)

        dossier_status = projet.dossier_ds.ds_state
        if dossier_status == Dossier.STATE_ACCEPTE:
            return cls._update_enveloppe_projets_from_projet_accepted(projet)
        elif dossier_status == Dossier.STATE_REFUSE:
            return cls._update_enveloppe_projets_from_projet_refused(projet)
        elif dossier_status == Dossier.STATE_SANS_SUITE:
            return cls._update_enveloppe_projets_from_projet_sans_suite(projet)
        elif dossier_status in [
            Dossier.STATE_EN_CONSTRUCTION,
            Dossier.STATE_EN_INSTRUCTION,
        ]:
            cls._update_accepted_enveloppe_projets_montant_from_dn(projet)
            is_dossier_back_to_instruction = cls._is_dossier_back_to_instruction(projet)
            if is_dossier_back_to_instruction:
                return cls._update_enveloppe_projets_from_projet_back_to_instruction(
                    projet
                )
        else:
            raise ValueError(f"Invalid dossier status: {dossier_status}")
        return projet.enveloppeprojet_set.all()

    @classmethod
    def _update_enveloppe_projets_from_projet_accepted(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        dotations_to_accept = cls._get_dotations_from_field(
            projet,
            "annotations_dotation",
            log_message_if_missing="No dotations found in annotations_dotation for accepted dossier during update",
        )

        if not dotations_to_accept:
            return projet.enveloppeprojet_set.all()

        existing_dotations = set(projet.dotations)
        dotations_to_remove = existing_dotations - set(dotations_to_accept)

        for dotation in dotations_to_accept:
            cls._accept_enveloppe_projet(projet, dotation)
            if dotation not in existing_dotations:
                ProjetAction.objects.create(
                    projet=projet,
                    action_type=ProjetAction.TYPE_DOTATION_ADDED,
                    actor=None,
                    source=ProjetAction.SOURCE_DN,
                    dotation=dotation,
                )

        for dotation in dotations_to_remove:
            deleted_count, _ = (
                EnveloppeProjet.objects.filter(projet=projet, dotation=dotation)
                .exclude(status__in=[ProjetStatus.REFUSED, ProjetStatus.DISMISSED])
                .delete()
            )
            if deleted_count:
                ProjetAction.objects.create(
                    projet=projet,
                    action_type=ProjetAction.TYPE_DOTATION_REMOVED,
                    actor=None,
                    source=ProjetAction.SOURCE_DN,
                    dotation=dotation,
                )

        return projet.enveloppeprojet_set.all()

    @classmethod
    def _accept_enveloppe_projet(
        cls, projet: Projet, dotation: POSSIBLE_DOTATIONS
    ) -> EnveloppeProjet:
        enveloppe_projet, _ = EnveloppeProjet.objects.get_or_create(
            projet=projet,
            dotation=dotation,
        )

        assiette = cls._get_assiette_from_annotations(projet.dossier_ds, dotation)
        if assiette is not None:  # we only update if we have an info
            enveloppe_projet.assiette = assiette

        detr_avis_commission = cls._get_detr_avis_commission(
            dotation, projet.dossier_ds
        )
        if detr_avis_commission is not None:  # we only update if we have an info
            enveloppe_projet.detr_avis_commission = detr_avis_commission

        if enveloppe_projet.is_programmee:  # We keep previous enveloppe to avoid squashing manuel rectification (ex: enveloppe 2025)
            enveloppe = enveloppe_projet.enveloppe
        else:
            enveloppe = cls._get_root_enveloppe_from_enveloppe_projet(enveloppe_projet)
        montant = cls._get_montant_from_dossier(projet.dossier_ds, dotation)
        enveloppe_projet.accept_without_ds_update(montant=montant, enveloppe=enveloppe)
        enveloppe_projet.save()

        return enveloppe_projet

    @classmethod
    def _update_enveloppe_projets_from_projet_refused(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        enveloppe_projets = []
        for enveloppe_projet in projet.enveloppeprojet_set.all():
            if enveloppe_projet.status != ProjetStatus.REFUSED:
                enveloppe = cls._get_root_enveloppe_from_enveloppe_projet(
                    enveloppe_projet, allow_next_year=True
                )
                enveloppe_projet.refuse(enveloppe=enveloppe)
                enveloppe_projet.save()
            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    @classmethod
    def _update_enveloppe_projets_from_projet_sans_suite(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        enveloppe_projets = []
        for enveloppe_projet in projet.enveloppeprojet_set.all():
            if enveloppe_projet.status not in [
                ProjetStatus.DISMISSED,
                ProjetStatus.REFUSED,
            ]:
                enveloppe = cls._get_root_enveloppe_from_enveloppe_projet(
                    enveloppe_projet, allow_next_year=True
                )
                enveloppe_projet.dismiss(enveloppe=enveloppe)
                enveloppe_projet.save()
            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    @classmethod
    def _update_enveloppe_projets_from_projet_back_to_instruction(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        projet_dps = projet.enveloppeprojet_set

        if projet_dps.filter(status=ProjetStatus.ACCEPTED).count() == 1:
            if (
                projet_dps.filter(
                    status__in=[ProjetStatus.DISMISSED, ProjetStatus.REFUSED]
                ).count()
                == 1
            ):
                return cls._update_enveloppe_projets_with_one_accepted_and_one_dismissed_or_refused(
                    projet
                )

        enveloppe_projets = []
        for enveloppe_projet in projet_dps.all():
            if cls._is_programmation_date_after_passage_en_instruction(
                enveloppe_projet
            ):
                enveloppe_projets.append(enveloppe_projet)
                continue

            if enveloppe_projet.status != ProjetStatus.PROCESSING:
                enveloppe_projet.set_back_status_to_processing_without_ds()
                enveloppe_projet.save()

            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    @classmethod
    def _update_enveloppe_projets_with_one_accepted_and_one_dismissed_or_refused(
        cls, projet: Projet
    ) -> list[EnveloppeProjet]:
        enveloppe_projets = []
        for enveloppe_projet in projet.enveloppeprojet_set.all():
            if enveloppe_projet.status == ProjetStatus.ACCEPTED:
                if cls._is_programmation_date_after_passage_en_instruction(
                    enveloppe_projet
                ):
                    continue
                enveloppe_projet.set_back_status_to_processing_without_ds()
                enveloppe_projet.save()
            enveloppe_projets.append(enveloppe_projet)
        return enveloppe_projets

    ## -------------------------- Utils --------------------------

    @classmethod
    def _update_accepted_enveloppe_projets_montant_from_dn(cls, projet: Projet) -> None:
        for enveloppe_projet in projet.enveloppeprojet_set.filter(
            status=ProjetStatus.ACCEPTED
        ):
            # Assiette is already updated (cf cls._update_assiette_from_dossier(projet) called in cls._update_enveloppe_projets_from_projet)
            # regardless of the projet/dossier statuses

            if enveloppe_projet.dotation == DOTATION_DETR:
                new_montant = projet.dossier_ds.annotations_montant_accorde_detr
            else:
                new_montant = projet.dossier_ds.annotations_montant_accorde_dsil

            if (
                new_montant is not None
                and enveloppe_projet.is_programmee
                and new_montant != enveloppe_projet.montant
            ):
                enveloppe_projet.accept_without_ds_update(
                    montant=new_montant,
                    enveloppe=enveloppe_projet.enveloppe,
                )
                enveloppe_projet.save()

    @classmethod
    def _get_detr_avis_commission(cls, dotation: str, ds_dossier: Dossier):
        if dotation == DOTATION_DETR and ds_dossier.ds_state == Dossier.STATE_ACCEPTE:
            return True

        return None

    @classmethod
    def _get_root_enveloppe_from_enveloppe_projet(
        cls, enveloppe_projet: EnveloppeProjet, allow_next_year: bool = False
    ):
        """
        Get the root enveloppe from a enveloppe projet.
        Args:
            allow_next_year: If True, allow the use of the next year if the dossier is accepted after November.
        """

        year = enveloppe_projet.dossier_ds.ds_date_traitement.year
        if (
            allow_next_year
            and enveloppe_projet.dossier_ds.ds_date_traitement.month >= 11
        ):
            year = year + 1

        enveloppe_qs = Enveloppe.objects.filter(
            dotation=enveloppe_projet.dotation,
            annee=year,
            parent__isnull=True,
        )
        projet_perimetre = enveloppe_projet.projet.perimetre
        perimetre = cls._get_perimetre_from_dotation(
            projet_perimetre, enveloppe_projet.dotation
        )
        try:
            return enveloppe_qs.get(perimetre=perimetre)
        except Enveloppe.DoesNotExist:
            logger.warning(
                "No enveloppe found for a enveloppe projet",
                extra={
                    "dossier_ds_number": enveloppe_projet.dossier_ds.ds_number,
                    "dotation": enveloppe_projet.dotation,
                    "year": year,
                    "perimetre": projet_perimetre,
                    "date_traitement": enveloppe_projet.dossier_ds.ds_date_traitement,
                },
            )
            raise Enveloppe.DoesNotExist(
                f"No enveloppe found for dotation {enveloppe_projet.dotation}, perimetre {projet_perimetre} and year {year}"
            )

    @classmethod
    def _get_perimetre_from_dotation(
        cls, projet_perimetre: Perimetre, dotation: str
    ) -> Perimetre | None:
        if dotation == DOTATION_DETR:
            return Perimetre.objects.get(
                departement=projet_perimetre.departement, arrondissement=None
            )

        elif dotation == DOTATION_DSIL:
            return Perimetre.objects.get(
                region=projet_perimetre.departement.region,
                departement=None,
                arrondissement=None,
            )

        return None

    @classmethod
    def _update_assiette_from_dossier(cls, projet: Projet):
        for enveloppe_projet in projet.enveloppeprojet_set.all():
            assiette = cls._get_assiette_from_annotations(
                projet.dossier_ds, enveloppe_projet.dotation
            )
            if assiette is None:
                continue

            if enveloppe_projet.assiette != assiette:
                ProjetAction.objects.create(
                    projet=projet,
                    action_type=ProjetAction.TYPE_ASSIETTE_MODIFIED,
                    actor=None,
                    source=ProjetAction.SOURCE_DN,
                    dotation=enveloppe_projet.dotation,
                    euro_field_value=assiette,
                )

            enveloppe_projet.assiette = assiette
            enveloppe_projet.save()

    @classmethod
    def _get_assiette_from_annotations(
        cls,
        dossier: Dossier,
        dotation: POSSIBLE_DOTATIONS,
    ) -> float | None:
        if dotation == DOTATION_DETR:
            return dossier.annotations_assiette_detr

        return dossier.annotations_assiette_dsil

    @classmethod
    def _get_montant_from_dossier(cls, dossier: Dossier, dotation: POSSIBLE_DOTATIONS):
        if dotation == DOTATION_DETR:
            montant = dossier.annotations_montant_accorde_detr
        elif dotation == DOTATION_DSIL:
            montant = dossier.annotations_montant_accorde_dsil
        if montant is None:
            logger.warning(
                "Montant is missing in dossier annotations",
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "dotation": dotation,
                },
            )
            return 0
        return montant

    @classmethod
    def _get_dotations_from_field(
        cls,
        projet: Projet,
        field: Literal[
            "annotations_dotation", "demande_dispositif_sollicite"
        ] = "annotations_dotation",
        log_message_if_missing: str = "No dotation",
    ) -> list[Any]:
        dotations_value = getattr(projet.dossier_ds, field)
        dotations: list[Any] = []

        if not dotations_value or dotations_value == "[]":
            logger.warning(
                log_message_if_missing,
                extra={
                    "dossier_ds_number": projet.dossier_ds.ds_number,
                    "projet": projet.pk,
                    "value": dotations_value,
                    "field": field,
                },
            )
            return dotations

        if DOTATION_DETR in dotations_value:
            dotations.append(DOTATION_DETR)
        if DOTATION_DSIL in dotations_value:
            dotations.append(DOTATION_DSIL)

        if not dotations:
            logger.warning(
                "Dotation unknown",
                extra={
                    "dossier_ds_number": projet.dossier_ds.ds_number,
                    "projet": projet.pk,
                    "value": dotations_value,
                    "field": field,
                },
            )
        return dotations

    @classmethod
    def _is_programmation_date_after_passage_en_instruction(
        cls, enveloppe_projet: EnveloppeProjet
    ):
        return (
            enveloppe_projet.is_programmee
            and enveloppe_projet.date_programmation
            > enveloppe_projet.projet.dossier_ds.ds_date_passage_en_instruction
        )

    @classmethod
    def _add_enveloppe_projets_to_all_concerned_simulations(
        cls, enveloppe_projets: list[EnveloppeProjet]
    ):
        from gsl.simulation.services.simulation_projet_service import (
            SimulationProjetService,
        )

        for enveloppe_projet in enveloppe_projets:
            simulations = cls._get_all_concerned_simulations_for_enveloppe_projet(
                enveloppe_projet
            ).exclude(simulationprojet__enveloppe_projet=enveloppe_projet)
            for simulation in simulations:
                SimulationProjetService.create_or_update_simulation_projet_from_enveloppe_projet(
                    enveloppe_projet, simulation
                )

    @classmethod
    def _get_all_concerned_simulations_for_enveloppe_projet(
        cls, enveloppe_projet: EnveloppeProjet
    ):
        qs = Simulation.objects.containing_perimetre(
            enveloppe_projet.projet.perimetre
        ).filter(
            enveloppe__dotation=enveloppe_projet.dotation,
            enveloppe__annee__gte=date.today().year,
        )

        if (
            enveloppe_projet.dossier_ds.ds_state
            in [Dossier.STATE_ACCEPTE, Dossier.STATE_SANS_SUITE, Dossier.STATE_REFUSE]
            and enveloppe_projet.dossier_ds.ds_date_traitement is not None
        ):
            qs = qs.exclude(
                enveloppe__annee__gte=enveloppe_projet.projet.dossier_ds.ds_date_traitement.year
                + 1,
            )

        if enveloppe_projet.is_programmee:
            qs = qs.exclude(enveloppe__annee__gt=enveloppe_projet.enveloppe.annee)

        return qs

    @classmethod
    def _remove_enveloppe_projets_from_unconcerned_simulations(
        cls, enveloppe_projets: list[EnveloppeProjet]
    ):
        for enveloppe_projet in enveloppe_projets:
            concerned_simulations = (
                cls._get_all_concerned_simulations_for_enveloppe_projet(
                    enveloppe_projet
                )
            )
            SimulationProjet.objects.filter(enveloppe_projet=enveloppe_projet).exclude(
                simulation__in=concerned_simulations
            ).delete()

    @classmethod
    def _should_dotations_be_updated_from_dn_construction_dossier(
        cls, projet: Projet
    ) -> bool:
        if projet.dotations_updated_in_app:
            # Once dotations have been updated in Turgot, we don't update dotations from DN
            return False

        if projet.dossier_ds.ds_state != Dossier.STATE_EN_CONSTRUCTION:
            # Dotations can only be updated for in construction dossiers
            return False

        # get the elements that are in one set but not in the other
        symetrical_difference = set(projet.dotations) ^ set(
            projet.dossier_ds.dotations_demande
        )
        return bool(symetrical_difference)

    @classmethod
    def _remove_or_add_dotations_from_dossier_ds(cls, projet: Projet):
        dotation_to_delete = set(projet.dotations) - set(
            projet.dossier_ds.dotations_demande
        )
        for dotation in dotation_to_delete:
            ProjetAction.objects.create(
                projet=projet,
                action_type=ProjetAction.TYPE_DOTATION_REMOVED,
                actor=None,
                source=ProjetAction.SOURCE_DN,
                dotation=dotation,
            )
        projet.enveloppeprojet_set.filter(dotation__in=dotation_to_delete).delete()

        # Refresh projet to get the latest dotations
        projet.refresh_from_db()

        dotations_to_add = set(projet.dossier_ds.dotations_demande) - set(
            projet.dotations
        )
        for dotation in dotations_to_add:
            cls._create_enveloppe_projet(projet, dotation)
            ProjetAction.objects.create(
                projet=projet,
                action_type=ProjetAction.TYPE_DOTATION_ADDED,
                actor=None,
                source=ProjetAction.SOURCE_DN,
                dotation=dotation,
            )

        # Idem here
        projet.refresh_from_db()

    @classmethod
    def _is_dossier_back_to_instruction(cls, projet: Projet) -> bool:
        date_traitement = projet.dossier_ds.ds_date_traitement
        date_passage_en_instruction = projet.dossier_ds.ds_date_passage_en_instruction
        if date_traitement is None or date_passage_en_instruction is None:
            return False

        return date_traitement < date_passage_en_instruction
