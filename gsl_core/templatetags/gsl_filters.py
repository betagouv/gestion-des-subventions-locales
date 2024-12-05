from decimal import Decimal

from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def percent(value, decimals=0):
    if not isinstance(value, Decimal):
        return value
    """Removes all values of arg from the given string"""
    return floatformat(value * Decimal("100.0"), decimals) + " %"
