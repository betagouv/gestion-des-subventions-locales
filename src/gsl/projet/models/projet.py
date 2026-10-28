from typing import TYPE_CHECKING, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    OuterRef,
    Q,
    Sum,
    Value,
    When,
)

from dn.sync.models import Dossier, Dotation
from gsl.core.campagne import CAMPAGNES
from gsl.core.models import Adresse, BaseModel, Collegue, Departement, Perimetre
from gsl.historique.models import ProjetAction
from gsl.notification.models import (
    GENERATED_DOCUMENTS,
    UPLOADED_DOCUMENTS,
)
from gsl.programmation.models import Enveloppe

from ..constants import MIN_DEMANDE_MONTANT_FOR_AVIS_DETR, ProjetStatus
from .enveloppe_projet import EnveloppeProjet
from .mixins import ProjetDNActionsMixin

if TYPE_CHECKING:
    from dn.sync.models import Dossier


class ProjetQuerySet(models.QuerySet):
    def for_user(self, user: Collegue):
        if user.perimetre is None:
            if user.is_staff or user.is_superuser:
                return self
            return self.none()

        return self.for_perimetre(user.perimetre)

    def annotate_status(self, campagne: int):
        enveloppe_projets = EnveloppeProjet.objects.filter(
            projet=OuterRef("pk"), enveloppe__annee=campagne
        )
        return self.annotate(
            _status=Case(
                # If not all dotations have programmation, return PROCESSING
                When(
                    Exists(enveloppe_projets.filter(status=ProjetStatus.PROCESSING)),
                    then=Value(ProjetStatus.PROCESSING),
                ),
                # If any dotation is ACCEPTED, return ACCEPTED
                When(
                    Exists(enveloppe_projets.filter(status=ProjetStatus.ACCEPTED)),
                    then=Value(ProjetStatus.ACCEPTED),
                ),
                # If any dotation is DISMISSED, return DISMISSED
                When(
                    Exists(enveloppe_projets.filter(status=ProjetStatus.DISMISSED)),
                    then=Value(ProjetStatus.DISMISSED),
                ),
                # If any dotation is REFUSED, return REFUSED
                When(
                    Exists(enveloppe_projets.filter(status=ProjetStatus.REFUSED)),
                    then=Value(ProjetStatus.REFUSED),
                ),
                # Projects without any EnveloppeProjet in the campagne have no status
                default=Value(None),
            )
        )

    def for_perimetre(self, perimetre: Perimetre | None):
        if perimetre is None:
            return self
        if perimetre.arrondissement:
            return self.filter(
                dossier_ds__perimetre__arrondissement=perimetre.arrondissement
            )
        if perimetre.departement:
            return self.filter(dossier_ds__perimetre__departement=perimetre.departement)
        if perimetre.region:
            return self.filter(dossier_ds__perimetre__region=perimetre.region)

    def for_campagne(self, annee: int):
        return self.filter(
            Exists(
                EnveloppeProjet.objects.filter(
                    projet=OuterRef("pk"), enveloppe__annee=annee
                )
            )
        )

    def to_notify(self):
        return self.annotate(
            dotations_count=Count("enveloppeprojet"),
            programmation_count=Count(
                "enveloppeprojet",
                filter=Q(enveloppeprojet__status__in=ProjetStatus.FINAL),
            ),
        ).filter(
            dotations_count__gt=0,
            dotations_count=F("programmation_count"),
            notified_at__isnull=True,
        )

    def with_at_least_one_treated_dotation(self):
        return self.filter(
            Exists(
                EnveloppeProjet.objects.programmees().filter(
                    projet=OuterRef("pk"),
                    status__in=ProjetStatus.FINAL,
                )
            )
        )

    def with_at_least_one_accepted_dotation(self):
        return self.filter(
            Exists(
                EnveloppeProjet.objects.filter(
                    projet=OuterRef("pk"), status=ProjetStatus.ACCEPTED
                )
            )
        )

    def with_missing_annotations(self):
        """Projets dont le dossier DS est accepté mais a des annotations DETR/DSIL incomplètes."""
        return self.filter(
            dossier_ds__ds_state=Dossier.State.ACCEPTE,
        ).filter(
            Q(dossier_ds__annotations_dotation="")
            | Q(dossier_ds__annotations_dotation="[]")
            | Q(dossier_ds__annotations_dotation__isnull=True)
            | (
                Q(dossier_ds__annotations_dotation__contains="DETR")
                & (
                    Q(dossier_ds__annotations_assiette_detr__isnull=True)
                    | Q(dossier_ds__annotations_montant_accorde_detr__isnull=True)
                )
            )
            | (
                Q(dossier_ds__annotations_dotation__contains="DSIL")
                & (
                    Q(dossier_ds__annotations_assiette_dsil__isnull=True)
                    | Q(dossier_ds__annotations_montant_accorde_dsil__isnull=True)
                )
            )
        )

    def totals(self):

        if getattr(self, "_totals", None) is None:
            self._totals = self.aggregate(
                total_cost=Sum("dossier_ds__finance_cout_total"),
                total_amount_asked=Sum("dossier_ds__demande_montant"),
                total_amount_granted=Sum(
                    "enveloppeprojet__montant",
                    filter=Q(enveloppeprojet__status=ProjetStatus.ACCEPTED),
                ),
            )

        return self._totals

    def active(self):
        return self.filter(dossier_ds__is_active=True)

    def has_document_ready(self):
        """Projets dont toutes les dotations sont traitées, et dont chaque
        dotation acceptée a son document signé importé."""
        return self.filter(
            Exists(EnveloppeProjet.objects.filter(projet=OuterRef("pk")))
        ).exclude(
            Exists(
                EnveloppeProjet.objects.filter(projet=OuterRef("pk")).filter(
                    Q(status=ProjetStatus.PROCESSING)
                    | Q(
                        status=ProjetStatus.ACCEPTED,
                        lettre_et_arrete_signes__isnull=True,
                    )
                )
            )
        )

    def accepted(self):
        return self.with_at_least_one_accepted_dotation().exclude(
            Exists(
                EnveloppeProjet.objects.filter(
                    projet=OuterRef("pk"), status=ProjetStatus.PROCESSING
                )
            )
        )


class ProjetManager(models.Manager.from_queryset(ProjetQuerySet)):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("dossier_ds")
            .prefetch_related("enveloppeprojet_set")
        )


class Projet(ProjetDNActionsMixin, BaseModel):
    dossier_ds = models.OneToOneField(Dossier, on_delete=models.PROTECT)

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT, null=True)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT, null=True)

    notified_at = models.DateTimeField(
        verbose_name="Date de notification", null=True, blank=True
    )

    is_in_qpv = models.BooleanField("Projet situé en QPV", null=False, default=False)
    is_attached_to_a_crte = models.BooleanField(
        "Projet rattaché à un CRTE",
        null=False,
        default=False,
    )
    is_budget_vert = models.BooleanField(
        "Projet concourant à la transition écologique au sens budget vert",
        null=False,
        default=False,
    )
    is_frr = models.BooleanField(
        "Projet situé en FRR",
        null=False,
        default=False,
    )
    is_acv = models.BooleanField(
        "Projet rattaché à un programme Action coeurs de Ville (ACV)",
        null=False,
        default=False,
    )
    is_pvd = models.BooleanField(
        "Projet rattaché à un programme Petites villes de demain (PVD)",
        null=False,
        default=False,
    )
    is_va = models.BooleanField(
        "Projet rattaché à un programme Villages d'avenir",
        null=False,
        default=False,
    )
    is_autre_zonage_local = models.BooleanField(
        "Projet rattaché à un autre zonage local",
        null=False,
        default=False,
    )
    autre_zonage_local = models.CharField("Nom du zonage local", blank=True)
    is_contrat_local = models.BooleanField(
        "Projet rattaché à un contrat local",
        null=False,
        default=False,
    )
    contrat_local = models.CharField("Nom du contrat local", blank=True)
    comment_1 = models.TextField("Commentaire 1", blank=True, default="")
    comment_2 = models.TextField("Commentaire 2", blank=True, default="")
    comment_3 = models.TextField("Commentaire 3", blank=True, default="")

    dotations_updated_in_app = models.BooleanField(
        "Dotations modifiées dans Turgot",
        null=False,
        default=False,
    )

    objects = ProjetManager()

    def __str__(self):
        return f"Projet {self.pk} — Dossier {self.dossier_ds.ds_number}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("projet:get-projet", kwargs={"projet_id": self.id})

    @property
    def perimetre(self):
        return self.dossier_ds.perimetre

    def root_enveloppe(self, dotation: str, annee: int) -> Enveloppe:
        return Enveloppe.objects.root_for(dotation, self.perimetre, annee)

    @property
    def campagne(self) -> int | None:
        """The campagne of its enveloppe projets, none if they span several."""
        annees = {ep.enveloppe.annee for ep in self.enveloppeprojet_set.all()}
        if len(annees) != 1:
            return None
        (annee,) = annees
        return annee

    @property
    def campagne_ouverte(self) -> int | None:
        """The most recent campagne of its enveloppe projets."""
        return max(
            (ep.enveloppe.annee for ep in self.enveloppeprojet_set.all()), default=None
        )

    @property
    def campagnes_de_bascule(self) -> list[int]:
        """The adjacent campagnes existing in Turgot, none if the projet spans
        several campagnes."""
        actuelle = self.campagne
        if actuelle is None:
            return []
        return [
            campagne
            for campagne in (actuelle - 1, actuelle + 1)
            if campagne in CAMPAGNES
        ]

    @transaction.atomic
    def basculer(self, campagne: int, actor: Collegue | None = None) -> None:
        """Moves the whole projet, history included, to an adjacent campagne: its
        enveloppe projets are kept, only their enveloppe changes."""
        from gsl.simulation.models import SimulationProjet

        if campagne not in self.campagnes_de_bascule:
            raise ValidationError(
                f"Ce projet ne peut pas être basculé sur la campagne {campagne}."
            )

        origine = self.campagne
        for enveloppe_projet in EnveloppeProjet.all_objects.filter(projet=self):
            enveloppe_projet.enveloppe = self.root_enveloppe(
                enveloppe_projet.dotation, campagne
            )
            enveloppe_projet.save(update_fields=["enveloppe"])
            if not enveloppe_projet.is_courant:
                continue
            SimulationProjet.objects.reset_for_enveloppe_projet(enveloppe_projet)
            ProjetAction.objects.create(
                projet=self,
                action_type=ProjetAction.TYPE_BASCULE,
                source=ProjetAction.SOURCE_TURGOT,
                actor=actor,
                dotation=enveloppe_projet.dotation,
                enveloppe=enveloppe_projet.enveloppe,
                details=str(origine),
            )

    def status_for(self, campagne: int) -> str | None:
        """Derived from its enveloppe projets of the campagne only."""
        return projet_status_from_dotation_statuses(
            [
                enveloppe_projet.status
                for enveloppe_projet in self.enveloppeprojet_set.all()
                if enveloppe_projet.enveloppe.annee == campagne
            ]
        )

    @property
    def demande_montant_is_greater_than_min_montant_for_detr_commission(self) -> bool:
        demande_montant = self.dossier_ds.demande_montant
        return (
            demande_montant is not None
            and demande_montant >= MIN_DEMANDE_MONTANT_FOR_AVIS_DETR
        )

    @property
    def can_have_a_commission_detr_avis(self) -> bool:
        return (
            self.enveloppeprojet_set.for_dotation(Dotation.DETR).exists()
            and self.demande_montant_is_greater_than_min_montant_for_detr_commission
        )

    @property
    def dotations(self) -> list[Dotation]:
        return sorted(
            [
                dotation.dotation
                for dotation in self.enveloppeprojet_set.all()
                if dotation.dotation in [Dotation.DETR, Dotation.DSIL]
            ]
        )

    @property
    def has_double_dotations(self):
        return self.enveloppeprojet_set.count() > 1

    @property
    def dotation_detr(self):
        for dp in self.enveloppeprojet_set.all():
            if dp.dotation == Dotation.DETR:
                return dp

    @property
    def dotation_dsil(self):
        for dp in self.enveloppeprojet_set.all():
            if dp.dotation == Dotation.DSIL:
                return dp

    @property
    def has_been_notified(self) -> bool:
        return self.notified_at is not None

    @property
    def to_notify(self) -> bool:
        if self.has_been_notified:
            return False

        enveloppe_projets = self.enveloppeprojet_set.all()
        if not enveloppe_projets:
            return False

        return all(dp.is_treated for dp in enveloppe_projets)

    @property
    def has_treated_dotation(self) -> bool:
        return any(dp.is_treated for dp in self.enveloppeprojet_set.all())

    @property
    def has_accepted_dotation(self) -> bool:
        return any(
            dp.status == ProjetStatus.ACCEPTED for dp in self.enveloppeprojet_set.all()
        )

    @property
    def can_display_notification_tab(self) -> bool:
        return self.has_treated_dotation

    @property
    def can_display_suivi_financier_tab(self) -> bool:
        return self.has_accepted_dotation

    @property
    def dotation_not_treated(self) -> Optional[Dotation]:
        # Python-side sort so we benefit from the enveloppeprojet_set
        # prefetch instead of re-querying via order_by().
        return next(
            (
                dp.dotation
                for dp in sorted(
                    self.enveloppeprojet_set.all(), key=lambda dp: dp.dotation
                )
                if dp.status == ProjetStatus.PROCESSING
            ),
            None,
        )

    @property
    def all_dotations_have_processing_status(self) -> bool:
        return all(
            dp.status == ProjetStatus.PROCESSING
            for dp in self.enveloppeprojet_set.all()
        )

    @property
    def generated_documents(self):
        documents = [
            document
            for model in GENERATED_DOCUMENTS.values()
            for document in model.objects.filter(
                enveloppe_projet__projet=self
            ).select_related(*_GENERATED_DOCUMENT_SELECT_RELATED)
        ]
        return sorted(
            documents,
            key=lambda d: (
                Dotation.values.index(d.enveloppe_projet.dotation),
                list(GENERATED_DOCUMENTS.keys()).index(d.document_type),
            ),
        )

    @property
    def imported_documents(self):
        documents = [
            document
            for model in UPLOADED_DOCUMENTS.values()
            for document in model.objects.filter(
                enveloppe_projet__projet=self
            ).select_related(*_UPLOADED_DOCUMENT_SELECT_RELATED)
        ]
        return sorted(
            documents,
            key=lambda d: (
                Dotation.values.index(d.enveloppe_projet.dotation),
                list(UPLOADED_DOCUMENTS.keys()).index(d.document_type),
            ),
        )

    @property
    def areas_and_contracts_provided_by_instructor(self) -> List[str]:
        ZONAGE_AND_CONTRACTS_FIELDS = [
            "is_in_qpv",
            "is_attached_to_a_crte",
            "is_frr",
            "is_acv",
            "is_pvd",
            "is_va",
            "is_autre_zonage_local",
            "is_contrat_local",
        ]

        return [
            self._meta.get_field(field).verbose_name
            for field in ZONAGE_AND_CONTRACTS_FIELDS
            if getattr(self, field)
        ]


# Used to construct file name
_GENERATED_DOCUMENT_SELECT_RELATED = (
    "enveloppe_projet__projet__dossier_ds__ds_demandeur",
)

# Used for dotation column
_UPLOADED_DOCUMENT_SELECT_RELATED = ("enveloppe_projet__enveloppe",)


def projet_status_from_dotation_statuses(
    statuses: List[str] | Tuple[str],
) -> str | None:
    from gsl.simulation.models import SimulationProjet

    if not statuses:
        return None

    if any(
        status == ProjetStatus.PROCESSING
        or status == SimulationProjet.STATUS_PROCESSING
        for status in statuses
    ):
        return ProjetStatus.PROCESSING

    if any(
        status == ProjetStatus.ACCEPTED or status == SimulationProjet.STATUS_ACCEPTED
        for status in statuses
    ):
        return ProjetStatus.ACCEPTED

    if any(
        status == ProjetStatus.DISMISSED or status == SimulationProjet.STATUS_DISMISSED
        for status in statuses
    ):
        return ProjetStatus.DISMISSED

    return ProjetStatus.REFUSED
