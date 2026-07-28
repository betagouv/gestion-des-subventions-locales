from django import template

from gsl_notification.forms import NotificationMessageForm

register = template.Library()


@register.inclusion_tag("includes/_notification_message_form.html", takes_context=True)
def notification_message_form(context, projet):
    print("ZIZOU")
    print(context["request"].user)
    print(projet.dossier_ds.is_instructeur(context["request"].user))
    return {
        "projet": projet,
        "form": NotificationMessageForm(instance=projet),
        "is_instructor": projet.dossier_ds.is_instructeur(context["request"].user),
    }
