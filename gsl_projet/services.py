from decimal import Decimal, InvalidOperation

from django.db.models import Case, F, Sum, When
from django.db.models.query import QuerySet

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.models import Demandeur, Projet


class ProjetService:
    @classmethod
    def create_or_update_from_ds_dossier(cls, ds_dossier: Dossier):
        try:
            projet = Projet.objects.get(dossier_ds=ds_dossier)
        except Projet.DoesNotExist:
            projet = Projet(
                dossier_ds=ds_dossier,
            )
        projet.address = ds_dossier.projet_adresse
        projet.perimetre = ds_dossier.perimetre
        projet.avis_commission_detr = cls.get_avis_commission_detr(ds_dossier)
        projet.is_in_qpv = cls.get_is_in_qpv(ds_dossier)
        projet.is_attached_to_a_crte = cls.get_is_attached_to_a_crte(ds_dossier)

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
        from gsl_programmation.models import ProgrammationProjet

        projet_ids = projet_qs.values_list("pk", flat=True)
        return ProgrammationProjet.objects.filter(
            projet__in=projet_ids, status=ProgrammationProjet.STATUS_ACCEPTED
        ).aggregate(total=Sum("montant"))["total"]

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
        try:
            new_taux = round(
                (Decimal(new_montant) / Decimal(projet.assiette_or_cout_total)) * 100,
                2,
            )
            return max(min(new_taux, Decimal(100)), Decimal(0))
        except TypeError:
            return Decimal(0)
        except ZeroDivisionError:
            return Decimal(0)
        except InvalidOperation:
            return Decimal(0)

    @classmethod
    def validate_taux(cls, taux: float | Decimal) -> None:
        if type(taux) not in [float, Decimal, int] or taux < 0 or taux > 100:
            raise ValueError(f"Taux {taux} must be between 0 and 100")

    @classmethod
    def validate_montant(cls, montant: float | Decimal, projet: Projet) -> None:
        if (
            type(montant) not in [float, Decimal, int]
            or montant < 0
            or projet.assiette_or_cout_total is None
            or montant > projet.assiette_or_cout_total
        ):
            raise ValueError(
                f"Montant {montant} must be greatear or equal to 0 and less than or equal to {projet.assiette_or_cout_total}"
            )

    @classmethod
    def get_avis_commission_detr(cls, ds_dossier: Dossier):
        if ds_dossier.ds_state == Dossier.STATE_ACCEPTE:
            if "DETR" in ds_dossier.demande_dispositif_sollicite:
                return True
        return None

    @classmethod
    def get_is_in_qpv(cls, ds_dossier: Dossier) -> bool:
        return bool(ds_dossier.annotations_is_qpv)

    @classmethod
    def get_is_attached_to_a_crte(cls, ds_dossier: Dossier) -> bool:
        return bool(ds_dossier.annotations_is_crte)
