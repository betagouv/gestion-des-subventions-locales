from django.db.models import Q

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe


class EnveloppeService:
    @classmethod
    def get_enveloppes_from_perimetre(cls, perimetre: Perimetre):
        if perimetre.type == Perimetre.TYPE_REGION:
            return Enveloppe.objects.filter(
                perimetre__region=perimetre.region,
                perimetre__departement=None,
                perimetre__arrondissement=None,
                type=Enveloppe.TYPE_DSIL,
            )

        return Enveloppe.objects.filter(
            Q(
                perimetre__region=perimetre.region,
                perimetre__departement=perimetre.departement,
                perimetre__arrondissement=None,
                type=Enveloppe.TYPE_DETR,
            )
            | Q(
                perimetre__region=perimetre.region,
                perimetre__departement=perimetre.departement,
                perimetre__arrondissement=None,
                type=Enveloppe.TYPE_DSIL,
            )
        )
