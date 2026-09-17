from datetime import datetime
from logging import getLogger

logger = getLogger(__name__)


def most_recent_traitement(traitements: list[dict], event: str) -> dict | None:
    """Retourne, parmi une liste de Traitement DN (dicts avec au moins un
    champ `dateTraitement`), celui dont la date est la plus récente. Les
    entrées sans `dateTraitement` exploitable sont ignorées. `None` si
    `traitements` est vide ou ne contient aucune date exploitable.

    `event` est l'événement attendu pour ce traitement le plus récent (ex :
    "accepte" juste après une mutation d'acceptation). Si le traitement
    trouvé a un `event` différent, l'incohérence est journalisée.
    """
    most_recent = None
    most_recent_date = None
    for traitement in traitements:
        raw_date_traitement = traitement.get("dateTraitement")
        if not raw_date_traitement:
            continue
        traitement_date = datetime.fromisoformat(raw_date_traitement)
        if most_recent_date is None or traitement_date > most_recent_date:
            most_recent_date = traitement_date
            most_recent = traitement

    if most_recent is not None and most_recent.get("event") != event:
        logger.exception(
            "Le traitement DN le plus récent ne correspond pas à l'événement attendu.",
            extra={
                "expected_event": event,
                "traitement_event": most_recent.get("event"),
                "traitement_id": most_recent.get("id"),
            },
        )
        return None

    return most_recent
