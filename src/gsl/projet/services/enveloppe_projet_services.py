import logging

from django.db import transaction

from dn.sync.models import Dossier, Dotation
from gsl.historique.models import ProjetAction
from gsl.simulation.models import SimulationProjet

from ..constants import ProjetStatus
from ..models import EnveloppeProjet, Projet

logger = logging.getLogger(__name__)


class EnveloppeProjetService:
    @classmethod
    @transaction.atomic
    def create_or_update_enveloppe_projet_from_projet(cls, projet: Projet) -> None:
        # The closed ones belong to the campagne the projet was reporté from.
        existing = {
            ep.dotation: ep
            for ep in projet.enveloppeprojet_set.in_most_recent_campagne()
        }
        is_initialisation = not existing
        campagne = cls._campagne_of_new_dotations(projet, existing.values())
        dotations = cls._expected_dotations(projet, set(existing))

        not_expected = existing.keys() - dotations
        for dotation in not_expected:
            enveloppe_projet = existing[dotation]
            if projet.dossier_ds.ds_state == Dossier.State.ACCEPTE:
                # An accepted dossier only annotates its accepted dotations: keep the others' refusal.
                if enveloppe_projet.status in ProjetStatus.NEGATIVE:
                    continue
                if enveloppe_projet.status == ProjetStatus.ACCEPTED:
                    existing[dotation] = cls._close_from_dn(
                        enveloppe_projet, EnveloppeProjet.refuse
                    )
                    continue
            cls._remove_dotation(existing.pop(dotation))

        to_create = sorted(dotations - existing.keys())
        for dotation in to_create:
            existing[dotation] = EnveloppeProjet.objects.create_for(
                projet,
                projet.root_enveloppe(dotation, campagne),
            )
            if not is_initialisation:
                ProjetAction.objects.create(
                    projet=projet,
                    action_type=ProjetAction.TYPE_DOTATION_ADDED,
                    actor=None,
                    source=ProjetAction.SOURCE_DN,
                    dotation=dotation,
                )

        cls._apply_dossier_state(projet, list(existing.values()), dotations)

        # We changed the courant EnveloppeProjets, make sure to fetch the latest
        # (without using the cached enveloppeprojet_set)
        for enveloppe_projet in EnveloppeProjet.objects.filter(projet=projet):
            enveloppe_projet.update_assiette_from_dn()
            enveloppe_projet.update_ej_from_dn()
            SimulationProjet.objects.reset_for_enveloppe_projet(enveloppe_projet)

        cls._update_notified_at(projet)

    # private

    ## -------------------------- Dotations --------------------------

    @classmethod
    def _expected_dotations(
        cls, projet: Projet, existing: set[Dotation]
    ) -> set[Dotation]:
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
    def _campagne_of_new_dotations(cls, projet: Projet, recents) -> int:
        """A reporté projet goes on on the campagne it was reporté to."""
        if recents and projet.enveloppeprojet_set.is_multi_campagnes():
            return max(ep.enveloppe.annee for ep in recents)
        return projet.dossier_ds.annee_de_campagne

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
        dotations: set[Dotation],
    ) -> None:
        dossier = projet.dossier_ds
        if dossier.ds_state == Dossier.State.ACCEPTE:
            cls._apply_accepted_dossier(dossier, enveloppe_projets, dotations)

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
        dotations: set[Dotation],
    ) -> None:
        for enveloppe_projet in enveloppe_projets:
            # Without annotated dotations, DN says nothing about the ones already
            # decided in Turgot: only the processing ones get accepted.
            if enveloppe_projet.dotation in dotations and (
                dossier.dotations_annotees
                or enveloppe_projet.status == ProjetStatus.PROCESSING
            ):
                cls._accept_from_dn(enveloppe_projet)

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
            cls._close_from_dn(enveloppe_projet, transition)

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

    ## -------------------------- Notification --------------------------

    @classmethod
    def _update_notified_at(cls, projet: Projet) -> None:
        """Mirrors the DN treatment on the programmed enveloppe projets of the most recent campagne: the
        closed ones keep the date of their own campagne."""
        dossier = projet.dossier_ds
        enveloppe_projets = (
            EnveloppeProjet.objects.filter(projet=projet)
            .in_most_recent_campagne()
            .programmees()
        )
        if dossier.is_treated:
            enveloppe_projets.filter(notified_at__isnull=True).update(
                notified_at=dossier.ds_date_traitement
            )
        else:
            enveloppe_projets.update(notified_at=None)

    ## -------------------------- Transitions --------------------------

    @classmethod
    def _accept_from_dn(cls, enveloppe_projet: EnveloppeProjet) -> EnveloppeProjet:
        # An already accepted dotation is only updated (montant, enveloppe).
        if enveloppe_projet.status != ProjetStatus.ACCEPTED:
            enveloppe_projet = cls._reopened_if_treated(enveloppe_projet)
        enveloppe_projet.accept_from_dn()
        return enveloppe_projet

    @classmethod
    def _close_from_dn(
        cls, enveloppe_projet: EnveloppeProjet, transition
    ) -> EnveloppeProjet:
        enveloppe_projet = cls._reopened_if_treated(enveloppe_projet)
        enveloppe_projet.close_from_dn(transition)
        return enveloppe_projet

    @classmethod
    def _reopened_if_treated(cls, enveloppe_projet: EnveloppeProjet) -> EnveloppeProjet:
        if enveloppe_projet.status not in ProjetStatus.FINAL:
            return enveloppe_projet
        return EnveloppeProjet.objects.supersede(enveloppe_projet)
