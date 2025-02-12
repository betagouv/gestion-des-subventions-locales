from datetime import date
from typing import Any

from django.db.models import Q
from django.utils.text import slugify

from gsl_core.models import Perimetre
from gsl_programmation.models import Enveloppe
from gsl_projet.services import ProjetService
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

    # C'est une duplication de la logique instanciée par ProjetFilters.
    # L'idée serait de ne plus se servir de cette méthode en instanciant ProjetFilters avec les bons filtres.
    @classmethod
    def add_filters_to_projets_qs(cls, qs, filters: dict, simulation: Simulation):
        cout_min = filters.get("cout_min")
        if cout_min and cout_min.isnumeric():
            qs = qs.filter(
                Q(assiette__isnull=False, assiette__gte=cout_min)
                | Q(assiette__isnull=True, dossier_ds__finance_cout_total__gte=cout_min)
            )

        cout_max = filters.get("cout_max")
        if cout_max and cout_max.isnumeric():
            qs = qs.filter(
                Q(assiette__isnull=False, assiette__lte=cout_max)
                | Q(assiette__isnull=True, dossier_ds__finance_cout_total__lte=cout_max)
            )

        montant_demande_min = filters.get("montant_demande_min")
        if montant_demande_min and montant_demande_min.isnumeric():
            qs = qs.filter(dossier_ds__demande_montant__gte=montant_demande_min)

        montant_demande_max = filters.get("montant_demande_max")
        if montant_demande_max and montant_demande_max.isnumeric():
            qs = qs.filter(dossier_ds__demande_montant__lte=montant_demande_max)

        montant_previsionnel_min = filters.get("montant_previsionnel_min")
        if montant_previsionnel_min and montant_previsionnel_min.isnumeric():
            qs = qs.filter(
                simulationprojet__simulation=simulation,
                simulationprojet__montant__gte=montant_previsionnel_min,
            )

        montant_previsionnel_max = filters.get("montant_previsionnel_max")
        if montant_previsionnel_max and montant_previsionnel_max.isnumeric():
            qs = qs.filter(
                simulationprojet__simulation=simulation,
                simulationprojet__montant__lte=montant_previsionnel_max,
            )

        status = filters.get("status")
        if status:
            qs = qs.filter(
                simulationprojet__simulation=simulation,
                simulationprojet__status__in=status,
            )

        porteur = filters.get("porteur")
        if porteur in ProjetService.PORTEUR_MAPPINGS:
            qs = qs.filter(
                dossier_ds__porteur_de_projet_nature__label__in=ProjetService.PORTEUR_MAPPINGS.get(
                    porteur
                )
            )

        return qs
