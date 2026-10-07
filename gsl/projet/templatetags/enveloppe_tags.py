from django import template
from django.db.models import Count, Q, Sum

from ..constants import ProjetStatus
from ..models import EnveloppeProjet

register = template.Library()


@register.inclusion_tag("includes/_enveloppe_summary_line.html", takes_context=True)
def enveloppe_summary_line(
    context, enveloppe, level=1, hide_actions=False, oob_swap=False
):
    accepted = Q(status=ProjetStatus.ACCEPTED)
    summary = (
        EnveloppeProjet.objects.active()
        .for_perimetre(enveloppe.perimetre)
        .filter(enveloppe=enveloppe.delegation_root)
        .aggregate(
            montant_asked=Sum("projet__dossier_ds__demande_montant"),
            accepted_montant=Sum("montant", filter=accepted, default=0),
            validated_projets_count=Count("pk", filter=accepted),
            refused_projets_count=Count("pk", filter=Q(status=ProjetStatus.REFUSED)),
            demandeurs_count=Count("projet__dossier_ds__ds_demandeur", distinct=True),
            projets_count=Count("pk"),
        )
    )

    return {
        "enveloppe": enveloppe,
        "level": level,
        "hide_actions": hide_actions,
        "oob_swap": oob_swap,
        "csrf_token": context.get("csrf_token"),
        "reste_a_attribuer": enveloppe.montant - summary["accepted_montant"],
        **summary,
    }
