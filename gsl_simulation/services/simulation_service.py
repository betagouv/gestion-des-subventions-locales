from datetime import date
from typing import Any

from django.utils.text import slugify

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe
from gsl_simulation.models import Simulation


class SimulationService:
    @classmethod
    def create_simulation(cls, user: Any, title: str, dotation: str):
        user_perimetre = user.perimetre
        if user_perimetre is None:
            raise ValueError("User has no perimetre")

        if dotation == Enveloppe.TYPE_DETR:
            if user_perimetre.type == Perimetre.TYPE_REGION:
                raise ValueError("For a DETR simulation, user must have a departement")

        enveloppe, _ = Enveloppe.objects.get_or_create(
            perimetre=user_perimetre,
            type=dotation,
            annee=date.today().year,
            defaults={"montant": 0},
        )  # TODO: handle deleguee_by if needed
        slug = SimulationService.get_slug(title)
        simulation = Simulation.objects.create(
            title=title,
            enveloppe=enveloppe,
            slug=slug,
            created_by=user,
        )
        return simulation

    @classmethod
    def get_slug(cls, title: str):
        slug = slugify(title)
        if Simulation.objects.filter(slug=slug).exists():
            i = 1
            incremented_slug = slugify(slug + f"-{i}")
            while Simulation.objects.filter(slug=incremented_slug).exists():
                i += 1
                incremented_slug = slugify(slug + f"-{i}")
            return incremented_slug
        return slug
