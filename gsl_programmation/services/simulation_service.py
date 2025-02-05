from datetime import date
from typing import Any

from django.utils.text import slugify

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe
from gsl_projet.models import Projet
from gsl_simulation.models import Simulation


class SimulationService:
    @classmethod
    def create_simulation(cls, user: Any, title: str, dotation: str):
        perimetre = user.perimetre
        if perimetre is None:
            raise ValueError("User has no perimetre")

        if dotation == Enveloppe.TYPE_DETR:
            if perimetre.type == Perimetre.TYPE_REGION:
                raise ValueError("User has no departement")

            perimetre_to_find = Perimetre.objects.get(
                departement=perimetre.departement,
                arrondissement=None,
            )
        else:
            perimetre_to_find = Perimetre.objects.get(
                region=perimetre.region,
                departement=None,
                arrondissement=None,
            )

        enveloppe, _ = Enveloppe.objects.get_or_create(
            perimetre=perimetre_to_find,
            type=dotation,
            annee=date.today().year,
            defaults={"montant": 0},
        )
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

    @classmethod
    def get_projets_from_simulation(cls, simulation: Simulation):
        return Projet.objects.filter(simulationprojet__simulation=simulation)
