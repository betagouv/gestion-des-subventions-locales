from django import template

from gsl_notification.forms import (
    GenerateDotationsDocumentsForm,
    NotificationMessageForm,
)

register = template.Library()


@register.inclusion_tag("includes/_notification_message_form.html", takes_context=True)
def notification_message_form(context, projet):
    return {
        "projet": projet,
        "form": NotificationMessageForm(instance=projet),
        "is_instructor": projet.dossier_ds.is_instructeur(context["request"].user),
    }


@register.inclusion_tag("includes/_generate_documents_form.html", takes_context=True)
def generate_documents_form(context, projet):
    return {
        "projet": projet,
        "form": GenerateDotationsDocumentsForm(
            projet=projet, user=context["request"].user
        ),
    }
