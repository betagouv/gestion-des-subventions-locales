from django import template

from gsl.core.bulk_actions import WIZARDS

register = template.Library()


@register.filter
def bulk_actions(enveloppe_projet):
    return " ".join(
        action
        for action, wizard in WIZARDS.items()
        if wizard.launch_form.applies_to(enveloppe_projet)
    )
