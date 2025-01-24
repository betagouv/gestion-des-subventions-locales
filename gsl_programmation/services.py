from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Case, F, Q, Sum, When
from django.db.models.query import QuerySet
from django.utils.text import slugify

from gsl_core.models import Perimetre
from gsl_demarches_simplifiees.models import NaturePorteurProjet
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


# TODO Move this to this service to gsl_project/services.py
class ProjetService:
    @classmethod
    def get_total_cost(cls, projet_qs: QuerySet):
        projets = projet_qs.annotate(
            calculed_cost=Case(
                When(assiette__isnull=False, then=F("assiette")),
                default=F("dossier_ds__finance_cout_total"),
            )
        )

        return projets.aggregate(total=Sum("calculed_cost"))["total"]

    @classmethod
    def get_total_amount_asked(cls, projet_qs: QuerySet):
        return projet_qs.aggregate(Sum("dossier_ds__demande_montant"))[
            "dossier_ds__demande_montant__sum"
        ]

    @classmethod
    def get_total_amount_granted(cls, projet_qs: QuerySet):
        return projet_qs.aggregate(Sum("simulationprojet__montant"))[
            "simulationprojet__montant__sum"
        ]

    PORTEUR_MAPPINGS = {
        "EPCI": NaturePorteurProjet.EPCI_NATURES,
        "Communes": NaturePorteurProjet.COMMUNE_NATURES,
    }

    @classmethod
    def add_filters_to_projets_qs(cls, qs, filters: dict):
        dispositif = filters.get("dispositif")
        if dispositif:
            qs = qs.filter(dossier_ds__demande_dispositif_sollicite=dispositif)

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

        porteur = filters.get("porteur")
        if porteur in cls.PORTEUR_MAPPINGS:
            qs = qs.filter(
                dossier_ds__porteur_de_projet_nature__label__in=cls.PORTEUR_MAPPINGS.get(
                    porteur
                )
            )

        return qs

    @classmethod
    def add_ordering_to_projets_qs(cls, qs, ordering):
        ordering_arg = cls.get_ordering_arg(ordering)
        if ordering_arg:
            qs = qs.order_by(ordering_arg)
        return qs

    @classmethod
    def get_ordering_arg(cls, ordering):
        ordering_map = {
            "date_desc": "-dossier_ds__ds_date_depot",
            "date_asc": "dossier_ds__ds_date_depot",
            "cout_desc": "-dossier_ds__finance_cout_total",
            "cout_asc": "dossier_ds__finance_cout_total",
            "commune_desc": "-address__commune__name",
            "commune_asc": "address__commune__name",
        }

        return ordering_map.get(ordering, None)
