from datetime import datetime


def most_recent_traitement(traitements: list[dict]) -> dict | None:
    """Retourne, parmi une liste de Traitement DN (dicts avec au moins un
    champ `dateTraitement`), celui dont la date est la plus récente. Les
    entrées sans `dateTraitement` exploitable sont ignorées. `None` si
    `traitements` est vide ou ne contient aucune date exploitable."""
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
    return most_recent
