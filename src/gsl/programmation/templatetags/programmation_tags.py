from django import template

from gsl.notification.forms.bulk_generation import (
    GenerateAcceptedDocumentsLaunchForm,
    GenerateRefusLettersLaunchForm,
)

register = template.Library()

BULK_ACTION_FORMS = [
    GenerateAcceptedDocumentsLaunchForm,
    GenerateRefusLettersLaunchForm,
]


@register.filter
def bulk_actions(enveloppe_projet):
    return " ".join(
        launch_form.action
        for launch_form in BULK_ACTION_FORMS
        if launch_form.applies_to(enveloppe_projet)
    )
