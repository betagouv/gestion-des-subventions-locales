from gsl_core.models import Collegue, Perimetre
from gsl_programmation.models import Enveloppe
from gsl_projet.constants import DOTATION_DSIL


class EnveloppeService:
    @classmethod
    def get_enveloppes_visible_for_a_user(cls, user: Collegue):
        if user.perimetre is None:
            if user.is_staff or user.is_superuser:
                return Enveloppe.objects.all()
            return Enveloppe.objects.none()

        return cls.get_enveloppes_from_perimetre(user.perimetre)

    @classmethod
    def get_enveloppes_from_perimetre(cls, perimetre: Perimetre | None):
        if perimetre is None:
            return Enveloppe.objects.all()

        if perimetre.type == Perimetre.TYPE_REGION:
            return Enveloppe.objects.filter(
                perimetre__region=perimetre.region,
                dotation=DOTATION_DSIL,
            )

        if perimetre.type == Perimetre.TYPE_DEPARTEMENT:
            return Enveloppe.objects.filter(
                perimetre__region=perimetre.region,
                perimetre__departement=perimetre.departement,
            )

        return Enveloppe.objects.filter(
            perimetre__region=perimetre.region,
            perimetre__departement=perimetre.departement,
            perimetre__arrondissement=perimetre.arrondissement,
        )

    @classmethod
    def get_parent_enveloppe(cls, enveloppe: Enveloppe):
        if not enveloppe.is_deleguee:
            return enveloppe
        else:
            return cls.get_parent_enveloppe(enveloppe.deleguee_by)
