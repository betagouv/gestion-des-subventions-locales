from datetime import UTC, date, datetime
from datetime import timezone as tz
from typing import TYPE_CHECKING, List, Optional, Tuple

from django.db import models
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

from gsl.core.models import Adresse, BaseModel, Collegue, Departement, Perimetre
from gsl.notification.models import (
    GENERATED_DOCUMENTS,
    UPLOADED_DOCUMENTS,
)
from gsl_demarches_simplifiees.models import Dossier

from ..constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
    MIN_DEMANDE_MONTANT_FOR_AVIS_DETR,
    POSSIBLE_DOTATIONS,
    ProjetStatus,
)
from .enveloppe_projet import EnveloppeProjet
from .mixins import ProjetDNActionsMixin

if TYPE_CHECKING:
    from gsl.programmation.models import Enveloppe
    from gsl_demarches_simplifiees.models import Dossier


class ProjetQuerySet(models.QuerySet):
    def for_user(self, user: Collegue):
        if user.perimetre is None:
            if user.is_staff or user.is_superuser:
                return self
            return self.none()

        return self.for_perimetre(user.perimetre)

    def annotate_status(self):
        has_processing = Exists(
            EnveloppeProjet.objects.filter(
                projet=OuterRef("pk"), status=ProjetStatus.PROCESSING
            )
        )

        # Count dotations with specific programmation status
        has_accepted = Exists(
            EnveloppeProjet.objects.filter(
                projet=OuterRef("pk"),
                status=ProjetStatus.ACCEPTED,
            )
        )

        has_dismissed = Exists(
            EnveloppeProjet.objects.filter(
                projet=OuterRef("pk"),
                status=ProjetStatus.DISMISSED,
            )
        )

        has_refused = Exists(
            EnveloppeProjet.objects.filter(
                projet=OuterRef("pk"),
                status=ProjetStatus.REFUSED,
            )
        )

        return self.annotate(
            _status=Case(
                # If not all dotations have programmation, return PROCESSING
                When(
                    has_processing,
                    then=Value(ProjetStatus.PROCESSING),
                ),
                # If any dotation is ACCEPTED, return ACCEPTED
                When(
                    has_accepted,
                    then=Value(ProjetStatus.ACCEPTED),
                ),
                # If any dotation is DISMISSED, return DISMISSED
                When(
                    has_dismissed,
                    then=Value(ProjetStatus.DISMISSED),
                ),
                # If any dotation is REFUSED, return REFUSED
                When(
                    has_refused,
                    then=Value(ProjetStatus.REFUSED),
                ),
                # Projects without any EnveloppeProjet have no status
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

    def for_current_year(self):
        return self.not_processed_before_the_start_of_the_year(date.today().year)

    def not_processed_before_the_start_of_the_year(self, year: int):
        return self.filter(
            Q(
                dossier_ds__ds_state__in=[
                    Dossier.State.EN_CONSTRUCTION,
                    Dossier.State.EN_INSTRUCTION,
                ]
            )
            | Q(
                dossier_ds__ds_state__in=[
                    Dossier.State.ACCEPTE,
                    Dossier.State.SANS_SUITE,
                    Dossier.State.REFUSE,
                ],
                dossier_ds__ds_date_traitement__gte=datetime(
                    year, 1, 1, 0, 0, tzinfo=tz.utc
                ),
            )
        )

    def included_in_enveloppe(self, enveloppe: "Enveloppe"):
        projet_qs = self.for_perimetre(enveloppe.perimetre)
        projet_qs_with_the_correct_dotation = projet_qs.filter(
            enveloppeprojet__dotation=enveloppe.dotation
        )
        projet_qs_submitted_before_the_end_of_the_year = (
            projet_qs_with_the_correct_dotation.filter(
                dossier_ds__ds_date_depot__lt=datetime(
                    enveloppe.annee + 1, 1, 1, tzinfo=UTC
                ),
            )
        )
        projet_qs_not_processed_before_the_start_of_the_year = projet_qs_submitted_before_the_end_of_the_year.not_processed_before_the_start_of_the_year(
            enveloppe.annee
        )
        return projet_qs_not_processed_before_the_start_of_the_year

    def to_notify(self):
        return self.annotate(
            dotations_count=Count("enveloppeprojet"),
            programmation_count=Count(
                "enveloppeprojet",
                filter=Q(enveloppeprojet__enveloppe__isnull=False),
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

    @property
    def status(self):
        if hasattr(self, "_status"):
            return self._status

        return projet_status_from_dotation_statuses(
            list(d.status for d in self.enveloppeprojet_set.all())
        )

    @property
    def can_have_a_commission_detr_avis(self) -> bool:
        return (
            self.enveloppeprojet_set.filter(dotation=DOTATION_DETR).exists()
            and self.dossier_ds.demande_montant is not None
            and self.dossier_ds.demande_montant >= MIN_DEMANDE_MONTANT_FOR_AVIS_DETR
        )

    @property
    def dotations(self) -> list[POSSIBLE_DOTATIONS]:
        return sorted(
            [
                dotation.dotation
                for dotation in self.enveloppeprojet_set.all()
                if dotation.dotation in [DOTATION_DETR, DOTATION_DSIL]
            ]
        )

    @property
    def has_double_dotations(self):
        return self.enveloppeprojet_set.count() > 1

    @property
    def dotation_detr(self):
        for dp in self.enveloppeprojet_set.all():
            if dp.dotation == DOTATION_DETR:
                return dp

    @property
    def dotation_dsil(self):
        for dp in self.enveloppeprojet_set.all():
            if dp.dotation == DOTATION_DSIL:
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
    def dotation_not_treated(self) -> Optional[POSSIBLE_DOTATIONS]:
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
                DOTATIONS.index(d.enveloppe_projet.dotation),
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
                DOTATIONS.index(d.enveloppe_projet.dotation),
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
_UPLOADED_DOCUMENT_SELECT_RELATED = ("enveloppe_projet",)


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
