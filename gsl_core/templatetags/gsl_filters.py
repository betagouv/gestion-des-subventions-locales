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
    return value.split(" ", 1)[1]


# TODO test
@register.filter
def create_alert_data_from_dict(value, arg):
    data_dict = {"is_collapsible": True}
    if value is None:
        data_dict["title"] = arg
        return data_dict

    data_dict["description"] = arg

    if value == "valid":
        data_dict["title"] = "Projet accepté"
    elif value == "cancelled":
        data_dict["title"] = "Projet refusé"

    return data_dict
