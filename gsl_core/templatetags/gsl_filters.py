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
