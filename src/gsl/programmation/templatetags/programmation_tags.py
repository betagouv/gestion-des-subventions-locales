from django import template

from gsl.notification.forms.bulk_generation import (
    GenerateAcceptedDocumentsLaunchForm,
    GenerateRefusLettersLaunchForm,
)
from gsl.notification.forms.bulk_notification import NotifyRefusLaunchForm

register = template.Library()

BULK_ACTION_FORMS = [
    GenerateAcceptedDocumentsLaunchForm,
    GenerateRefusLettersLaunchForm,
    NotifyRefusLaunchForm,
]


@register.filter
def bulk_actions(enveloppe_projet):
    return " ".join(
        launch_form.action
        for launch_form in BULK_ACTION_FORMS
        if launch_form.applies_to(enveloppe_projet)
    )
