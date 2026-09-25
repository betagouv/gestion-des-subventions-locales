from django import template

register = template.Library()


@register.filter
def custom_pluralize(value, suffix="s"):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return ""
    return suffix if value not in [0, 1] else ""
