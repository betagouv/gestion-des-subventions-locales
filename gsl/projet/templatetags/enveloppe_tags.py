from django import template
from django.db.models import Count, Sum

from ..constants import PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED
from ..models import EnveloppeProjet, Projet

register = template.Library()


@register.inclusion_tag("includes/_enveloppe_summary_line.html", takes_context=True)
def enveloppe_summary_line(
    context, enveloppe, level=1, hide_actions=False, oob_swap=False
):
    included = Projet.objects.active().included_in_enveloppe(enveloppe)
    if enveloppe.is_deleguee:
        processed = EnveloppeProjet.objects.active().filter(
            enveloppe=enveloppe.delegation_root, projet__in=included
        )
    else:
        processed = EnveloppeProjet.objects.active().filter(enveloppe=enveloppe)
    accepted = processed.filter(status=PROJET_STATUS_ACCEPTED)

    accepted_montant = accepted.aggregate(Sum("montant"))["montant__sum"] or 0
    return {
        "enveloppe": enveloppe,
        "level": level,
        "hide_actions": hide_actions,
        "oob_swap": oob_swap,
        "csrf_token": context.get("csrf_token"),
        "montant_asked": included.aggregate(Sum("dossier_ds__demande_montant"))[
            "dossier_ds__demande_montant__sum"
        ],
        "accepted_montant": accepted_montant,
        "reste_a_attribuer": enveloppe.montant - accepted_montant,
        "validated_projets_count": accepted.count(),
        "refused_projets_count": processed.filter(status=PROJET_STATUS_REFUSED).count(),
        "demandeurs_count": included.aggregate(
            count=Count("dossier_ds__ds_demandeur", distinct=True)
        )["count"],
        "projets_count": included.count(),
    }
