from datetime import date
from decimal import Decimal
from typing import Any

from django.utils.text import slugify

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe, Simulation, SimulationProjet
from gsl_projet.models import Projet


# TODO : split this file + add plural to service folder
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

        enveloppe = Enveloppe.objects.get(
            perimetre=perimetre_to_find, type=dotation, annee=date.today().year
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


class SimulationProjetService:
    @classmethod
    def update_status(cls, simulation_projet: SimulationProjet, new_status: str):
        simulation_projet.status = new_status
        simulation_projet.save()
        return simulation_projet

    @classmethod
    def update_taux(cls, simulation_projet: SimulationProjet, new_taux: float):
        new_montant = (
            simulation_projet.projet.assiette_or_cout_total * Decimal(new_taux) / 100
        )
        new_montant = round(new_montant, 2)

        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()

    @classmethod
    def update_montant(cls, simulation_projet, new_montant: float):
        new_taux = (
            Decimal(new_montant)
            / Decimal(simulation_projet.projet.assiette_or_cout_total)
        ) * 100
        new_taux = round(new_taux, 2)
        simulation_projet.taux = new_taux
        simulation_projet.montant = new_montant
        simulation_projet.save()
