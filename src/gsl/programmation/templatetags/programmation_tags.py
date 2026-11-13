from django import template

from gsl.notification.forms.bulk_generation import BULK_ACTIONS

register = template.Library()


@register.filter
def bulk_actions(enveloppe_projet):
    return " ".join(
        name
        for name, launch_form in BULK_ACTIONS.items()
        if launch_form.applies_to(enveloppe_projet)
    )
