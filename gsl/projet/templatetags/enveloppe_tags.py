from django import template
from django.db.models import Count, Sum

from ..constants import ProjetStatus
from ..models import EnveloppeProjet, Projet

register = template.Library()


@register.inclusion_tag("includes/_enveloppe_summary_line.html", takes_context=True)
def enveloppe_summary_line(
    context, enveloppe, level=1, hide_actions=False, oob_swap=False
):
    projets_included = Projet.objects.active().for_perimetre(enveloppe.perimetre)
    eps_included = EnveloppeProjet.objects.active().filter(
        projet__in=projets_included, enveloppe=enveloppe.delegation_root
    )

    processed = eps_included.filter(status__in=ProjetStatus.FINAL)

    accepted = eps_included.filter(status=ProjetStatus.ACCEPTED)
    accepted_montant = accepted.aggregate(Sum("montant"))["montant__sum"] or 0

    return {
        "enveloppe": enveloppe,
        "level": level,
        "hide_actions": hide_actions,
        "oob_swap": oob_swap,
        "csrf_token": context.get("csrf_token"),
        "montant_asked": eps_included.aggregate(
            sum=Sum("projet__dossier_ds__demande_montant")
        )["sum"],
        "accepted_montant": accepted_montant,
        "reste_a_attribuer": enveloppe.montant - accepted_montant,
        "validated_projets_count": accepted.count(),
        "refused_projets_count": processed.filter(status=ProjetStatus.REFUSED).count(),
        "demandeurs_count": eps_included.aggregate(
            count=Count("projet__dossier_ds__ds_demandeur", distinct=True)
        )["count"],
        "projets_count": eps_included.count(),
    }
