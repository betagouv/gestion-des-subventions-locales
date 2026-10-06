import logging

from django.db import transaction

from gsl.historique.models import ProjetAction
from gsl.simulation.models import SimulationProjet
from gsl_demarches_simplifiees.models import Dossier

from ..constants import (
    POSSIBLE_DOTATIONS,
    ProjetStatus,
)
from ..models import EnveloppeProjet, Projet

logger = logging.getLogger(__name__)


class EnveloppeProjetService:
    @classmethod
    @transaction.atomic
    def create_or_update_enveloppe_projet_from_projet(cls, projet: Projet) -> None:
        existing = {ep.dotation: ep for ep in projet.enveloppeprojet_set.all()}
        is_initialisation = not existing
        dotations = cls._expected_dotations(projet, set(existing))

        to_delete = existing.keys() - dotations
        for dotation in to_delete:
            # An accepted dossier only annotates its accepted dotations: keep the others' refusal.
            if (
                projet.dossier_ds.ds_state == Dossier.State.ACCEPTE
                and existing[dotation].status in ProjetStatus.NEGATIVE
            ):
                continue
            cls._remove_dotation(existing.pop(dotation))

        to_create = sorted(dotations - existing.keys())
        for dotation in to_create:
            existing[dotation] = EnveloppeProjet.objects.create_for(
                projet,
                projet.root_enveloppe(dotation, projet.dossier_ds.annee_de_campagne),
            )
            if not is_initialisation:
                ProjetAction.objects.create(
                    projet=projet,
                    action_type=ProjetAction.TYPE_DOTATION_ADDED,
                    actor=None,
                    source=ProjetAction.SOURCE_DN,
                    dotation=dotation,
                )

        enveloppe_projets = list(existing.values())
        for enveloppe_projet in enveloppe_projets:
            enveloppe_projet.update_assiette_from_dn()
        cls._apply_dossier_state(
            projet, enveloppe_projets, dotations, is_initialisation
        )

        for enveloppe_projet in enveloppe_projets:
            SimulationProjet.objects.reset_for_enveloppe_projet(enveloppe_projet)

    # private

    ## -------------------------- Dotations --------------------------

    @classmethod
    def _expected_dotations(
        cls, projet: Projet, existing: set[POSSIBLE_DOTATIONS]
    ) -> set[POSSIBLE_DOTATIONS]:
        dossier = projet.dossier_ds
        if dossier.ds_state == Dossier.State.ACCEPTE:
            if dossier.dotations_annotees:
                return set(dossier.dotations_annotees)
            logger.warning(
                "No dotations found in annotations_dotation for accepted dossier",
                extra={
                    "dossier_ds_number": dossier.ds_number,
                    "projet": projet.pk,
                    "value": dossier.annotations_dotation,
                    "field": "annotations_dotation",
                },
            )
            return existing or set(dossier.dotations_demande)

        if not existing or (
            dossier.ds_state == Dossier.State.EN_CONSTRUCTION
            and not projet.dotations_updated_in_app
        ):
            return set(dossier.dotations_demande)
        return existing

    @classmethod
    def _remove_dotation(cls, enveloppe_projet: EnveloppeProjet) -> None:
        ProjetAction.objects.create(
            projet=enveloppe_projet.projet,
            action_type=ProjetAction.TYPE_DOTATION_REMOVED,
            actor=None,
            source=ProjetAction.SOURCE_DN,
            dotation=enveloppe_projet.dotation,
        )
        enveloppe_projet.delete()

    ## -------------------------- Status --------------------------

    @classmethod
    def _apply_dossier_state(
        cls,
        projet: Projet,
        enveloppe_projets: list[EnveloppeProjet],
        dotations: set[POSSIBLE_DOTATIONS],
        is_initialisation: bool,  # TODO investigate if we still need this exception.
    ) -> None:
        dossier = projet.dossier_ds
        if dossier.ds_state == Dossier.State.ACCEPTE:
            cls._apply_accepted_dossier(
                dossier, enveloppe_projets, dotations, is_initialisation
            )

        elif dossier.ds_state == Dossier.State.REFUSE:
            cls._apply_refused_dossier(enveloppe_projets)

        elif dossier.ds_state == Dossier.State.SANS_SUITE:
            cls._apply_sans_suite_dossier(enveloppe_projets)

        elif dossier.ds_state in [
            Dossier.State.EN_CONSTRUCTION,
            Dossier.State.EN_INSTRUCTION,
        ]:
            cls._apply_undecided_dossier(dossier, enveloppe_projets)

        else:
            raise ValueError(f"Invalid dossier status: {dossier.ds_state}")

    @classmethod
    def _apply_accepted_dossier(
        cls,
        dossier: Dossier,
        enveloppe_projets: list[EnveloppeProjet],
        dotations: set[POSSIBLE_DOTATIONS],
        is_initialisation: bool,
    ) -> None:
        # An accepted dossier with no annotated dotation says nothing new about the
        # ones already known, so only the initial import falls back on the demande.
        if not (dossier.dotations_annotees or is_initialisation):
            return
        for enveloppe_projet in enveloppe_projets:
            if enveloppe_projet.dotation in dotations:
                enveloppe_projet.accept_from_dn()

    @classmethod
    def _apply_refused_dossier(cls, enveloppe_projets: list[EnveloppeProjet]) -> None:
        cls._close_enveloppe_projets(
            enveloppe_projets,
            EnveloppeProjet.refuse,
            unchanged_statuses=[ProjetStatus.REFUSED],
        )

    @classmethod
    def _apply_sans_suite_dossier(
        cls, enveloppe_projets: list[EnveloppeProjet]
    ) -> None:
        # A dotation already refused stays refused: a sans suite on the dossier does
        # not soften an individual refusal.
        cls._close_enveloppe_projets(
            enveloppe_projets,
            EnveloppeProjet.dismiss,
            unchanged_statuses=ProjetStatus.NEGATIVE,
        )

    @classmethod
    def _apply_undecided_dossier(
        cls, dossier: Dossier, enveloppe_projets: list[EnveloppeProjet]
    ) -> None:
        for enveloppe_projet in enveloppe_projets:
            if enveloppe_projet.status == ProjetStatus.ACCEPTED:
                enveloppe_projet.update_montant_from_dn()
        if dossier.is_retour_en_instruction:
            cls._reopen_after_passage_en_instruction(enveloppe_projets)

    @classmethod
    def _close_enveloppe_projets(
        cls,
        enveloppe_projets: list[EnveloppeProjet],
        transition,
        unchanged_statuses: list[str],
    ) -> None:
        for enveloppe_projet in enveloppe_projets:
            if enveloppe_projet.status in unchanged_statuses:
                continue
            enveloppe_projet.close_from_dn(transition)

    @classmethod
    def _reopen_after_passage_en_instruction(
        cls, enveloppe_projets: list[EnveloppeProjet]
    ) -> None:
        statuses = [enveloppe_projet.status for enveloppe_projet in enveloppe_projets]
        one_accepted_and_one_refused_or_dismissed = (
            statuses.count(ProjetStatus.ACCEPTED) == 1
            and sum(status in ProjetStatus.NEGATIVE for status in statuses) == 1
        )
        reopened_statuses = (
            [ProjetStatus.ACCEPTED]
            if one_accepted_and_one_refused_or_dismissed
            else ProjetStatus.FINAL
        )

        for ep in enveloppe_projets:
            if ep.status not in reopened_statuses:
                continue
            # Programmed in Turgot after DN reopened the instruction: so Turgot status
            # wins, nothing to undo.
            if ep.date_programmation > ep.dossier_ds.ds_date_passage_en_instruction:
                continue
            ep.set_back_status_to_processing_without_ds()
