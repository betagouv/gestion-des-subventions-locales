from decimal import Decimal

from django import template
from django.template.defaultfilters import floatformat

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


@register.filter
def create_alert_data(status: str | None, arg: str) -> dict[str, str | bool]:
    data_dict: dict[str, str | bool] = {"is_collapsible": True}
    if status is None:
        data_dict["title"] = arg
        return data_dict

    data_dict["description"] = arg

    if status == "valid":
        data_dict["title"] = "Projet accepté"
    elif status == "cancelled":
        data_dict["title"] = "Projet refusé"
    elif status == "provisoire":
        data_dict["title"] = "Projet accepté provisoirement"
    elif status == "dismissed":
        data_dict["title"] = "Projet classé sans suite"
    elif status == "draft":
        data_dict["title"] = "Projet en traitement"

    return data_dict
