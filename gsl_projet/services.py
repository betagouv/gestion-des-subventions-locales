from decimal import Decimal

from django.db.models import Case, F, Sum, When
from django.db.models.query import QuerySet

from gsl_demarches_simplifiees.models import Dossier, NaturePorteurProjet
from gsl_projet.models import Demandeur, Projet


class ProjetService:
    @classmethod
    def get_or_create_from_ds_dossier(cls, ds_dossier: Dossier):
        try:
            projet = Projet.objects.get(dossier_ds=ds_dossier)
        except Projet.DoesNotExist:
            projet = Projet(
                dossier_ds=ds_dossier,
            )
        projet.address = ds_dossier.projet_adresse
        projet.perimetre = ds_dossier.perimetre

        projet.demandeur, _ = Demandeur.objects.get_or_create(
            siret=ds_dossier.ds_demandeur.siret,
            defaults={
                "name": ds_dossier.ds_demandeur.raison_sociale,
                "address": ds_dossier.ds_demandeur.address,
            },
        )

        projet.status = cls.get_projet_status(ds_dossier)
        projet.save()
        return projet

    DOSSIER_DS_STATUS_TO_PROJET_STATUS = {
        Dossier.STATE_ACCEPTE: Projet.STATUS_ACCEPTED,
        Dossier.STATE_EN_CONSTRUCTION: Projet.STATUS_PROCESSING,
        Dossier.STATE_EN_INSTRUCTION: Projet.STATUS_PROCESSING,
        Dossier.STATE_REFUSE: Projet.STATUS_REFUSED,
        Dossier.STATE_SANS_SUITE: Projet.STATUS_DISMISSED,
    }

    @classmethod
    def get_projet_status(cls, ds_dossier):
        return cls.DOSSIER_DS_STATUS_TO_PROJET_STATUS.get(ds_dossier.ds_state)

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
    def add_ordering_to_projets_qs(cls, qs, ordering):
        default_ordering = "-dossier_ds__ds_date_depot"
        qs = qs.order_by(default_ordering)

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

    @classmethod
    def compute_taux_from_montant(
        cls, projet: Projet, new_montant: float | Decimal
    ) -> Decimal:
        new_taux = (
            round(
                (Decimal(new_montant) / Decimal(projet.assiette_or_cout_total)) * 100, 2
            )
            if projet.assiette_or_cout_total
            else Decimal(0)
        )
        return new_taux
