import re
from decimal import Decimal
from typing import Any

from django import template
from django.template.defaultfilters import floatformat

from gsl_simulation.models import SimulationProjet

register = template.Library()


@register.filter
def percent(value, decimals=0):
    if value is None:
        return "— %"
    if not isinstance(value, Decimal):
        return value
    """Removes all values of arg from the given string"""
    return floatformat(value, decimals) + " %"


@register.filter
def euro(value, decimals=0):
    if not isinstance(value, (float, int, Decimal)) or isinstance(value, bool):
        return "—"
    return floatformat(value, f"{decimals}g") + " €"


@register.filter
def remove_first_word(value):
    parts = value.split(" ", 1)
    return parts[1] if len(parts) > 1 else ""


STATUS_TO_ALERT_TITLE = {
    SimulationProjet.STATUS_ACCEPTED: "Projet accepté",
    SimulationProjet.STATUS_REFUSED: "Projet refusé",
    SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: "Projet accepté provisoirement",
    SimulationProjet.STATUS_PROVISIONALLY_REFUSED: "Projet refusé provisoirement",
    SimulationProjet.STATUS_DISMISSED: "Projet classé sans suite",
    SimulationProjet.STATUS_PROCESSING: "Projet en traitement",
}


@register.filter
def create_alert_data(message: Any) -> dict[str, str | bool]:
    data_dict = {
        "is_collapsible": True,
        "description": message.message,
    }

    if message.extra_tags in STATUS_TO_ALERT_TITLE:
        data_dict["title"] = STATUS_TO_ALERT_TITLE[message.extra_tags]
    elif message.extra_tags in ["info", "alert"]:
        data_dict["type"] = message.extra_tags

    return data_dict


@register.filter
def format_demandeur_nom(nom):
    MOTS_MIN = (
        "de",
        "du",
        "des",
        "sur",
        "et",
        "la",
        "le",
        "les",
        "d",
        "en",
        "l",
        "au",
        "aux",
        "a",
        "un",
        "une",
        "l",
    )
    ABREVIATIONS = ("cc", "ca", "cte")

    # Sépare les mots tout en conservant les tirets et les apostrophes
    mots = re.split(r"(\s+|-|\')", nom.lower().strip())

    resultat = []
    for mot in mots:
        if mot in ABREVIATIONS:
            resultat.append(mot.upper())
        elif mot.strip() in MOTS_MIN:
            resultat.append(mot.lower())  # Garde en minuscule
        else:
            resultat.append(mot.capitalize())  # Met la première lettre en majuscule

    # Correction de l'apostrophe
    texte_final = "".join(resultat)
    texte_final = texte_final.replace(" d ", " d'").replace(" d' ", " d'")

    return texte_final
