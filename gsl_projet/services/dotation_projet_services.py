import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from django.db import transaction

from gsl_core.models import Perimetre
from gsl_core.templatetags.gsl_filters import euro, percent
from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import Enveloppe
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    POSSIBLE_DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet, Projet
from gsl_simulation.models import Simulation

logger = logging.getLogger(__name__)


class DotationProjetService:
    @classmethod
    def create_or_update_dotation_projet_from_projet(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        # check for initialisation
        if projet.dotationprojet_set.count() == 0:
            dotation_projets = cls._initialize_dotation_projets_from_projet(projet)

        else:
            # check for updates
            dotation_projets = cls._update_dotation_projets_from_projet(projet)

        cls._add_dotation_projets_to_all_concerned_simulations(dotation_projets)
        return dotation_projets

    @classmethod
    def create_simulation_projets_from_dotation_projet(
        cls,
        dotation_projet: DotationProjet,
    ):
        from gsl_simulation.services.simulation_projet_service import (
            SimulationProjetService,
        )

        projet_perimetre = dotation_projet.projet.perimetre
        perimetres_containing_this_projet_perimetre = list(projet_perimetre.ancestors())
        perimetres_containing_this_projet_perimetre.append(projet_perimetre)
        enveloppes = Enveloppe.objects.filter(
            dotation=dotation_projet.dotation,
            perimetre__in=perimetres_containing_this_projet_perimetre,
            annee__gte=date.today().year,
        )
        simulations = Simulation.objects.filter(enveloppe__in=enveloppes)
        for simulation in simulations:
            SimulationProjetService.create_or_update_simulation_projet_from_dotation_projet(
                dotation_projet, simulation
            )

    @classmethod
    def compute_montant_from_taux(
        cls, dotation_projet: DotationProjet, new_taux: float | Decimal
    ) -> float | Decimal:
        try:
            assiette = dotation_projet.assiette_or_cout_total
            new_montant = (assiette * Decimal(new_taux) / 100) if assiette else 0
            new_montant = round(new_montant, 2)
            return max(min(new_montant, dotation_projet.assiette_or_cout_total), 0)
        except TypeError:
            return 0
        except InvalidOperation:
            return 0

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
                f"Le montant {euro(montant)} doit être supérieur ou égal à 0 € et inférieur ou égal à l'assiette ({euro(dotation_projet.assiette_or_cout_total)})."
            )

    @classmethod
    def validate_taux(cls, taux: float | Decimal) -> None:
        if type(taux) not in [float, Decimal, int] or taux < 0 or taux > 100:
            raise ValueError(f"Le taux {percent(taux)} doit être entre 0% and 100%")

    @classmethod
    def get_other_accepted_dotations(
        cls, dotation_projet: DotationProjet
    ) -> list[POSSIBLE_DOTATIONS]:
        return [
            dp.dotation
            for dp in dotation_projet.other_dotations
            if dp.status == PROJET_STATUS_ACCEPTED
        ]

    # private

    ## -------------------------- Initialize Dotation Projets --------------------------

    @classmethod
    @transaction.atomic
    def _initialize_dotation_projets_from_projet(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dossier_status = projet.dossier_ds.ds_state
        if dossier_status in (
            Dossier.STATE_ACCEPTE,
            Dossier.STATE_REFUSE,
            Dossier.STATE_SANS_SUITE,
        ):
            projet.notified_at = projet.dossier_ds.ds_date_traitement
            projet.save(update_fields=["notified_at"])

        if dossier_status == Dossier.STATE_ACCEPTE:
            return cls._initialize_dotation_projets_from_projet_accepted(projet)
        elif dossier_status == Dossier.STATE_REFUSE:
            return cls._initialize_dotation_projets_from_projet_refused(projet)
        elif dossier_status == Dossier.STATE_SANS_SUITE:
            return cls._initialize_dotation_projets_from_projet_sans_suite(projet)
        elif dossier_status in [
            Dossier.STATE_EN_CONSTRUCTION,
            Dossier.STATE_EN_INSTRUCTION,
        ]:
            return cls._initialize_dotation_projets_from_projet_en_construction_or_instruction(
                projet
            )

        raise ValueError(f"Invalid dossier status: {dossier_status}")

    @classmethod
    def _initialize_dotation_projets_from_projet_accepted(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotations = cls._get_dotations_from_field(
            projet,
            "annotations_dotation",
            log_message_if_missing="No dotations found in annotations_dotation for accepted dossier during initialisation",
        )

        if not dotations:
            dotations = cls._get_dotations_from_field(
                projet, "demande_dispositif_sollicite"
            )

        dotation_projets = []
        for dotation in dotations:
            dotation_projet = cls._create_dotation_projet(projet, dotation)
            enveloppe = cls._get_root_enveloppe_from_dotation_projet(dotation_projet)
            montant = cls._get_montant_from_dossier(projet.dossier_ds, dotation)
            dotation_projet.accept_without_ds_update(
                montant=montant, enveloppe=enveloppe
            )
            dotation_projet.save()
            dotation_projets.append(dotation_projet)
        return dotation_projets

    @classmethod
    def _initialize_dotation_projets_from_projet_refused(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotations = cls._get_dotations_from_field(
            projet, "demande_dispositif_sollicite"
        )
        dotation_projets = []
        for dotation in dotations:
            dotation_projet = cls._create_dotation_projet(projet, dotation)
            enveloppe = cls._get_root_enveloppe_from_dotation_projet(
                dotation_projet, allow_next_year=True
            )
            dotation_projet.refuse(enveloppe=enveloppe)
            dotation_projet.save()
            dotation_projets.append(dotation_projet)
        return dotation_projets

    @classmethod
    def _initialize_dotation_projets_from_projet_sans_suite(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotations = cls._get_dotations_from_field(
            projet, "demande_dispositif_sollicite"
        )
        dotation_projets = []
        for dotation in dotations:
            dotation_projet = cls._create_dotation_projet(projet, dotation)
            enveloppe = cls._get_root_enveloppe_from_dotation_projet(
                dotation_projet, allow_next_year=True
            )
            dotation_projet.dismiss(enveloppe=enveloppe)
            dotation_projet.save()
            dotation_projets.append(dotation_projet)
        return dotation_projets

    @classmethod
    def _initialize_dotation_projets_from_projet_en_construction_or_instruction(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotations = cls._get_dotations_from_field(
            projet, "demande_dispositif_sollicite"
        )
        dotation_projets = []
        for dotation in dotations:
            dotation_projet = cls._create_dotation_projet(projet, dotation)
            dotation_projets.append(dotation_projet)
        return dotation_projets

    @classmethod
    def _create_dotation_projet(
        cls, projet: Projet, dotation: POSSIBLE_DOTATIONS
    ) -> DotationProjet:
        detr_avis_commission = cls._get_detr_avis_commission(
            dotation, projet.dossier_ds
        )
        log_level = (
            logging.WARNING
            if projet.dossier_ds.ds_state == Dossier.STATE_ACCEPTE
            else logging.INFO
        )
        assiette = cls._get_assiette_from_dossier(
            projet.dossier_ds, dotation, log_level
        )
        return DotationProjet.objects.create(
            projet=projet,
            dotation=dotation,
            detr_avis_commission=detr_avis_commission,
            assiette=assiette,
        )

    ## -------------------------- Update Dotation Projets --------------------------

    @classmethod
    @transaction.atomic
    def _update_dotation_projets_from_projet(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        cls._update_assiette_from_dossier(projet)

        dossier_status = projet.dossier_ds.ds_state

        if dossier_status in (
            Dossier.STATE_ACCEPTE,
            Dossier.STATE_REFUSE,
            Dossier.STATE_SANS_SUITE,
        ):
            projet.notified_at = projet.dossier_ds.ds_date_traitement
            projet.save(update_fields=["notified_at"])

        if dossier_status == Dossier.STATE_ACCEPTE:
            return cls._update_dotation_projets_from_projet_accepted(projet)
        elif dossier_status == Dossier.STATE_REFUSE:
            return cls._update_dotation_projets_from_projet_refused(projet)
        elif dossier_status == Dossier.STATE_SANS_SUITE:
            return cls._update_dotation_projets_from_projet_sans_suite(projet)
        elif dossier_status in [
            Dossier.STATE_EN_CONSTRUCTION,
            Dossier.STATE_EN_INSTRUCTION,
        ]:
            date_traitement = projet.dossier_ds.ds_date_traitement
            date_passage_en_instruction = (
                projet.dossier_ds.ds_date_passage_en_instruction
            )
            if date_traitement is not None and date_passage_en_instruction is not None:
                is_dossier_back_to_instruction = (
                    date_traitement < date_passage_en_instruction
                )
                if is_dossier_back_to_instruction:
                    return cls._update_dotation_projets_from_projet_back_to_instruction(
                        projet
                    )
        else:
            raise ValueError(f"Invalid dossier status: {dossier_status}")
        return projet.dotationprojet_set.all()

    @classmethod
    def _update_dotation_projets_from_projet_accepted(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotations_to_accept = cls._get_dotations_from_field(
            projet,
            "annotations_dotation",
            log_message_if_missing="No dotations found in annotations_dotation for accepted dossier during update",
        )

        if not dotations_to_accept:
            return projet.dotationprojet_set.all()

        dotations_to_remove = set(projet.dotations) - set(dotations_to_accept)
        for dotation in dotations_to_accept:
            cls._accept_dotation_projet(projet, dotation)

        for dotation in dotations_to_remove:
            DotationProjet.objects.filter(projet=projet, dotation=dotation).exclude(
                status__in=[PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED]
            ).delete()

        return projet.dotationprojet_set.all()

    @classmethod
    def _accept_dotation_projet(
        cls, projet: Projet, dotation: POSSIBLE_DOTATIONS
    ) -> DotationProjet:
        dotation_projet, _ = DotationProjet.objects.get_or_create(
            projet=projet,
            dotation=dotation,
        )

        assiette = cls._get_assiette_from_dossier(projet.dossier_ds, dotation)
        if assiette is not None:  # we only update if we have an info
            dotation_projet.assiette = assiette

        detr_avis_commission = cls._get_detr_avis_commission(
            dotation, projet.dossier_ds
        )
        if detr_avis_commission is not None:  # we only update if we have an info
            dotation_projet.detr_avis_commission = detr_avis_commission

        enveloppe = cls._get_root_enveloppe_from_dotation_projet(dotation_projet)
        montant = cls._get_montant_from_dossier(projet.dossier_ds, dotation)
        dotation_projet.accept_without_ds_update(montant=montant, enveloppe=enveloppe)
        dotation_projet.save()

        return dotation_projet

    @classmethod
    def _update_dotation_projets_from_projet_refused(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotation_projets = []
        for dotation_projet in projet.dotationprojet_set.all():
            if dotation_projet.status != PROJET_STATUS_REFUSED:
                enveloppe = cls._get_root_enveloppe_from_dotation_projet(
                    dotation_projet, allow_next_year=True
                )
                dotation_projet.refuse(enveloppe=enveloppe)
                dotation_projet.save()
            dotation_projets.append(dotation_projet)
        return dotation_projets

    @classmethod
    def _update_dotation_projets_from_projet_sans_suite(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotation_projets = []
        for dotation_projet in projet.dotationprojet_set.all():
            if dotation_projet.status not in [
                PROJET_STATUS_DISMISSED,
                PROJET_STATUS_REFUSED,
            ]:
                enveloppe = cls._get_root_enveloppe_from_dotation_projet(
                    dotation_projet, allow_next_year=True
                )
                dotation_projet.dismiss(enveloppe=enveloppe)
                dotation_projet.save()
            dotation_projets.append(dotation_projet)
        return dotation_projets

    @classmethod
    def _update_dotation_projets_from_projet_back_to_instruction(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        projet_dps = projet.dotationprojet_set

        if projet_dps.filter(status=PROJET_STATUS_ACCEPTED).count() == 1:
            if (
                projet_dps.filter(
                    status__in=[PROJET_STATUS_DISMISSED, PROJET_STATUS_REFUSED]
                ).count()
                == 1
            ):
                return cls._update_dotation_projets_with_one_accepted_and_one_dismissed_or_refused(
                    projet
                )

        dotation_projets = []
        for dotation_projet in projet_dps.all():
            if cls._is_programmation_projet_created_after_date_of_passage_en_instruction(
                dotation_projet
            ):
                dotation_projets.append(dotation_projet)
                continue

            if dotation_projet.status != PROJET_STATUS_PROCESSING:
                dotation_projet.set_back_status_to_processing_without_ds()
                dotation_projet.save()

            dotation_projets.append(dotation_projet)
        return dotation_projets

    @classmethod
    def _update_dotation_projets_with_one_accepted_and_one_dismissed_or_refused(
        cls, projet: Projet
    ) -> list[DotationProjet]:
        dotation_projets = []
        for dotation_projet in projet.dotationprojet_set.all():
            if dotation_projet.status == PROJET_STATUS_ACCEPTED:
                if cls._is_programmation_projet_created_after_date_of_passage_en_instruction(
                    dotation_projet
                ):
                    continue
                dotation_projet.set_back_status_to_processing_without_ds()
                dotation_projet.save()
            dotation_projets.append(dotation_projet)
        return dotation_projets

    ## -------------------------- Utils --------------------------

    @classmethod
    def _get_detr_avis_commission(cls, dotation: str, ds_dossier: Dossier):
        if dotation == DOTATION_DETR and ds_dossier.ds_state == Dossier.STATE_ACCEPTE:
            return True

        return None

    @classmethod
    def _get_root_enveloppe_from_dotation_projet(
        cls, dotation_projet: DotationProjet, allow_next_year: bool = False
    ):
        """
        Get the root enveloppe from a dotation projet.
        Args:
            allow_next_year: If True, allow the use of the next year if the dossier is accepted after November.
        """

        year = dotation_projet.dossier_ds.ds_date_traitement.year
        if (
            allow_next_year
            and dotation_projet.dossier_ds.ds_date_traitement.month >= 11
        ):
            year = year + 1

        enveloppe_qs = Enveloppe.objects.filter(
            dotation=dotation_projet.dotation,
            annee=year,
            deleguee_by__isnull=True,
        )
        projet_perimetre = dotation_projet.projet.perimetre
        perimetre = cls._get_perimetre_from_dotation(
            projet_perimetre, dotation_projet.dotation
        )
        try:
            return enveloppe_qs.get(perimetre=perimetre)
        except Enveloppe.DoesNotExist:
            logger.warning(
                "No enveloppe found for a dotation projet",
                extra={
                    "dossier_ds_number": dotation_projet.dossier_ds.ds_number,
                    "dotation": dotation_projet.dotation,
                    "year": year,
                    "perimetre": projet_perimetre,
                    "date_traitement": dotation_projet.dossier_ds.ds_date_traitement,
                },
            )
            raise Enveloppe.DoesNotExist(
                f"No enveloppe found for dotation {dotation_projet.dotation}, perimetre {projet_perimetre} and year {year}"
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
        for dotation_projet in projet.dotationprojet_set.all():
            assiette = cls._get_assiette_from_dossier(
                projet.dossier_ds, dotation_projet.dotation
            )
            if assiette is not None:
                dotation_projet.assiette = assiette
            dotation_projet.save()

    @classmethod
    def _get_assiette_from_dossier(
        cls,
        dossier: Dossier,
        dotation: POSSIBLE_DOTATIONS,
        log_level: int = logging.WARNING,
    ) -> float | None:
        if dotation == DOTATION_DETR:
            assiette = dossier.annotations_assiette_detr
        elif dotation == DOTATION_DSIL:
            assiette = dossier.annotations_assiette_dsil

        if assiette is None:
            logger.log(
                log_level,
                "Assiette is missing in dossier annotations",
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "dotation": dotation,
                },
            )
            return None
        return assiette

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
    def _is_programmation_projet_created_after_date_of_passage_en_instruction(
        cls, dotation_projet: DotationProjet
    ):
        if (
            hasattr(dotation_projet, "programmation_projet")
            and dotation_projet.programmation_projet.created_at
            > dotation_projet.projet.dossier_ds.ds_date_passage_en_instruction
        ):
            return True
        return False

    @classmethod
    def _add_dotation_projets_to_all_concerned_simulations(
        cls, dotation_projets: list[DotationProjet]
    ):
        from gsl_simulation.services.simulation_projet_service import (
            SimulationProjetService,
        )

        for dotation_projet in dotation_projets:
            simulations = cls._get_simulation_concerning_by_this_dotation_projet(
                dotation_projet
            )
            for simulation in simulations:
                SimulationProjetService.create_or_update_simulation_projet_from_dotation_projet(
                    dotation_projet, simulation
                )

    @classmethod
    def _get_simulation_concerning_by_this_dotation_projet(
        cls, dotation_projet: DotationProjet
    ):
        qs = (
            Simulation.objects.containing_perimetre(dotation_projet.projet.perimetre)
            .filter(
                enveloppe__dotation=dotation_projet.dotation,
                enveloppe__annee__gte=date.today().year,
            )
            .exclude(simulationprojet__dotation_projet=dotation_projet)
        )

        if (
            dotation_projet.dossier_ds.ds_state
            in [Dossier.STATE_ACCEPTE, Dossier.STATE_SANS_SUITE, Dossier.STATE_REFUSE]
            and dotation_projet.dossier_ds.ds_date_traitement is not None
        ):
            qs = qs.exclude(
                enveloppe__annee__gte=dotation_projet.projet.dossier_ds.ds_date_traitement.year
                + 1,
            )
        return qs
