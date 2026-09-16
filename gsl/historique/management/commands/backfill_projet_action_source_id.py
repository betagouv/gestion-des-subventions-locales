import logging
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand

from gsl_demarches_simplifiees.importer.dossier import save_one_dossier_from_ds

from ...models import ProjetAction

logger = logging.getLogger(__name__)

MATCH_TOLERANCE = timedelta(seconds=5)


class Command(BaseCommand):
    """
    python manage.py backfill_projet_action_source_id

    Rattache un id de Traitement DN (ProjetAction.source_id) aux notifications
    déjà enregistrées avant l'introduction de ce champ, en resynchronisant
    chaque dossier concerné depuis Démarches Numériques. Les correspondances
    incertaines déclenchent une alerte admin plutôt que d'être devinées.
    """

    help = "Rattache ProjetAction.source_id aux notifications déjà enregistrées"

    def handle(self, *args, **options):
        logger.info("Backfill de ProjetAction.source_id…")
        actions = ProjetAction.objects.filter(
            action_type=ProjetAction.TYPE_NOTIFIED, source_id=""
        ).select_related("projet__dossier_ds")

        for action in actions:
            dossier = action.projet.dossier_ds  # faire un appel par seconde
            try:
                save_one_dossier_from_ds(dossier)
            except Exception as e:
                logger.error(
                    "Backfill ProjetAction.source_id : échec du rafraîchissement DN "
                    "du dossier #%s",
                    dossier.ds_number,
                    exc_info=e,
                )
                continue

            traitement = _find_traitement_matching_action(dossier, action)

            if traitement is not None:
                action.source_id = traitement["id"]
                action.save(update_fields=["source_id"])
            else:
                logger.warning(
                    f"Backfill ProjetAction.source_id : correspondance incertaine "
                    f"(dossier DN #{dossier.ds_number})\n"
                    f"ProjetAction #{action.pk} (projet #{action.projet_id}, créée le "
                    f"{action.created_at}) : aucun traitement DN trouvé à moins de "
                    f"{MATCH_TOLERANCE} de cette date. Vérification manuelle nécessaire."
                )
        logger.info(self.style.SUCCESS("Terminé."))


def _find_traitement_matching_action(dossier, action: ProjetAction) -> dict | None:
    """Parcourt tous les traitements du dossier (pas seulement celui
    correspondant à son état courant, cf. `get_last_traitement_matching_dossier_state`)
    et retourne celui dont `dateTraitement` est le plus proche de
    `action.created_at`, à condition d'être à moins de `MATCH_TOLERANCE`."""
    ds_data = getattr(dossier, "ds_data", None)
    traitements = ((ds_data.raw_data if ds_data else None) or {}).get(
        "traitements"
    ) or []

    best_match = None
    best_delta = None
    notification_traitements = [
        t
        for t in traitements
        if t.get("event") in ["accepte", "refuse", "classe_sans_suite"]
    ]
    for traitement in notification_traitements:
        traitement_id = traitement.get("id")
        date_traitement = traitement.get("dateTraitement")
        if not traitement_id or not date_traitement:
            continue
        delta = abs(datetime.fromisoformat(date_traitement) - action.created_at)
        if delta < MATCH_TOLERANCE and (best_delta is None or delta < best_delta):
            best_match = traitement
            best_delta = delta
    return best_match
