from datetime import UTC, date, datetime
from datetime import timezone as tz
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple, Union

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    OuterRef,
    Q,
    UniqueConstraint,
    Value,
    When,
)
from django_fsm import FSMField, transition

from gsl_core.models import Adresse, BaseModel, Collegue, Departement, Perimetre
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.services import DsService
from gsl_projet.constants import (
    DOTATION_CHOICES,
    DOTATION_DETR,
    DOTATION_DSIL,
    MIN_DEMANDE_MONTANT_FOR_AVIS_DETR,
    POSSIBLE_DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_CHOICES,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.utils.utils import floatize

if TYPE_CHECKING:
    from gsl_demarches_simplifiees.models import CritereEligibiliteDsil, Dossier
    from gsl_programmation.models import Enveloppe
    from gsl_simulation.models import SimulationProjet


class CategorieDetrQueryset(models.QuerySet):
    def current_for_departement(self, departement: Departement):
        return self.filter(departement=departement, is_current=True)


class CategorieDetr(models.Model):
    libelle = models.CharField("Libellé")
    rang = models.IntegerField("Rang", default=0)
    annee = models.IntegerField("Année")
    departement = models.ForeignKey(
        Departement, verbose_name="Département", on_delete=models.PROTECT
    )
    is_current = models.BooleanField(
        "Actuelle",
        help_text="Indique si cette catégorie est utilisable sur la campagne actuelle ou non",
        default=False,
    )

    objects = CategorieDetrQueryset.as_manager()

    class Meta:
        verbose_name = "Catégorie DETR"
        verbose_name_plural = "Catégories DETR"
        constraints = (
            UniqueConstraint(
                fields=("departement", "annee", "rang"),
                name="unique_by_departement_rang_annee",
            ),
        )

    def __str__(self):
        return f"Catégorie DETR {self.id} - {self.libelle}"

    @property
    def label(self):
        if self.libelle[0].isdigit():
            return self.libelle
        return f"{self.rang} - {self.libelle}"


class Demandeur(models.Model):
    siret = models.CharField("Siret", unique=True)
    name = models.CharField("Nom")

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT)

    def __str__(self):
        return f"Demandeur {self.name}"


class ProjetQuerySet(models.QuerySet):
    def for_user(self, user: Collegue):
        if user.perimetre is None:
            if user.is_staff or user.is_superuser:
                return self
            return self.none()

        return self.for_perimetre(user.perimetre)

    def annotate_status(self):
        # Check if all dotations have a programmation_projet
        has_processing = Exists(
            DotationProjet.objects.filter(
                projet=OuterRef("pk"), status=PROJET_STATUS_PROCESSING
            )
        )

        # Count dotations with specific programmation status
        has_accepted = Exists(
            DotationProjet.objects.filter(
                projet=OuterRef("pk"),
                status=PROJET_STATUS_ACCEPTED,
            )
        )

        has_dismissed = Exists(
            DotationProjet.objects.filter(
                projet=OuterRef("pk"),
                status=PROJET_STATUS_DISMISSED,
            )
        )

        return self.annotate(
            _status=Case(
                # If not all dotations have programmation, return PROCESSING
                When(
                    has_processing,
                    then=Value(PROJET_STATUS_PROCESSING),
                ),
                # If any dotation is ACCEPTED, return ACCEPTED
                When(
                    has_accepted,
                    then=Value(PROJET_STATUS_ACCEPTED),
                ),
                # If any dotation is DISMISSED, return DISMISSED
                When(
                    has_dismissed,
                    then=Value(PROJET_STATUS_DISMISSED),
                ),
                # Otherwise return REFUSED
                default=Value(PROJET_STATUS_REFUSED),
            )
        )

    def for_perimetre(self, perimetre: Perimetre | None):
        if perimetre is None:
            return self
        if perimetre.arrondissement:
            return self.filter(perimetre__arrondissement=perimetre.arrondissement)
        if perimetre.departement:
            return self.filter(perimetre__departement=perimetre.departement)
        if perimetre.region:
            return self.filter(perimetre__region=perimetre.region)

    def for_current_year(self):
        return self.not_processed_before_the_start_of_the_year(date.today().year)

    def not_processed_before_the_start_of_the_year(self, year: int):
        return self.filter(
            Q(
                dossier_ds__ds_state__in=[
                    Dossier.STATE_EN_CONSTRUCTION,
                    Dossier.STATE_EN_INSTRUCTION,
                ]
            )
            | Q(
                dossier_ds__ds_state__in=[
                    Dossier.STATE_ACCEPTE,
                    Dossier.STATE_SANS_SUITE,
                    Dossier.STATE_REFUSE,
                ],
                dossier_ds__ds_date_traitement__gte=datetime(
                    year, 1, 1, 0, 0, tzinfo=tz.utc
                ),
            )
        )

    def included_in_enveloppe(self, enveloppe: "Enveloppe"):
        projet_qs = self.for_perimetre(enveloppe.perimetre)
        projet_qs_with_the_correct_dotation = projet_qs.filter(
            dotationprojet__dotation=enveloppe.dotation
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
            dotations_count=Count("dotationprojet"),
            programmation_count=Count(
                "dotationprojet__programmation_projet",
            ),
        ).filter(dotations_count=F("programmation_count"), notified_at__isnull=True)

    def can_send_notification(self):
        return self.to_notify().exclude(
            dotationprojet__in=DotationProjet.objects.without_signed_document()
        )

    def with_at_least_one_programmed_dotation(self):
        from gsl_programmation.models import ProgrammationProjet

        return self.filter(
            Exists(
                ProgrammationProjet.objects.filter(
                    dotation_projet__projet=OuterRef("pk")
                )
            )
        )

    def with_at_least_one_accepted_dotation(self):
        from gsl_programmation.models import ProgrammationProjet

        return self.filter(
            Exists(
                ProgrammationProjet.objects.filter(
                    dotation_projet__projet=OuterRef("pk"),
                    status=PROJET_STATUS_ACCEPTED,
                )
            )
        )


class ProjetManager(models.Manager.from_queryset(ProjetQuerySet)):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("dossier_ds")
            .prefetch_related("dotationprojet_set")
        )


class Projet(models.Model):
    dossier_ds = models.OneToOneField(Dossier, on_delete=models.PROTECT)
    demandeur = models.ForeignKey(Demandeur, on_delete=models.PROTECT, null=True)

    address = models.ForeignKey(Adresse, on_delete=models.PROTECT, null=True)
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT, null=True)
    perimetre = models.ForeignKey(Perimetre, on_delete=models.PROTECT, null=True)

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
    free_comment = models.TextField("Commentaires libres", blank=True, default="")

    objects = ProjetManager()

    def __str__(self):
        return f"Projet {self.pk} — Dossier {self.dossier_ds.ds_number}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("projet:get-projet", kwargs={"projet_id": self.id})

    @property
    def status(self):
        if hasattr(self, "_status"):
            return self._status

        return projet_status_from_dotation_statuses(
            list(d.status for d in self.dotationprojet_set.all())
        )

    @property
    def can_have_a_commission_detr_avis(self) -> bool:
        return (
            self.dotationprojet_set.filter(dotation=DOTATION_DETR).exists()
            and self.dossier_ds.demande_montant is not None
            and self.dossier_ds.demande_montant >= MIN_DEMANDE_MONTANT_FOR_AVIS_DETR
        )

    @property
    def categories_doperation(
        self,
    ) -> Iterator[Union["CategorieDetr", "CritereEligibiliteDsil"]]:
        if self.dotation_detr:
            yield from self.dotation_detr.detr_categories.all()
        if DOTATION_DSIL in self.dossier_ds.demande_dispositif_sollicite:
            yield from self.dossier_ds.demande_eligibilite_dsil.all()

    @property
    def dotations(self) -> list[POSSIBLE_DOTATIONS]:
        return [
            dotation.dotation
            for dotation in self.dotationprojet_set.all()
            if dotation.dotation in [DOTATION_DETR, DOTATION_DSIL]
        ]

    @property
    def has_double_dotations(self):
        return self.dotationprojet_set.count() > 1

    @property
    def dotation_detr(self):
        for dp in self.dotationprojet_set.all():
            if dp.dotation == DOTATION_DETR:
                return dp

    @property
    def dotation_dsil(self):
        for dp in self.dotationprojet_set.all():
            if dp.dotation == DOTATION_DSIL:
                return dp

    @property
    def to_notify(self) -> bool:
        """
        Returns True if the projet has not been notified yet, and all dotations have a programmation.

        Does not check if the programmation has been accepted or refused ! This is not necessary.
        """
        return all(
            (
                hasattr(d, "programmation_projet")
                and d.programmation_projet.notified_at is None
            )
            for d in self.dotationprojet_set.all()
        )

    @property
    def can_send_notification(self) -> bool:
        return (
            self.to_notify
            and not self.dotationprojet_set.without_signed_document().exists()
        )

    @property
    def can_display_notification_tab(self) -> bool:
        return any(
            d.status == PROJET_STATUS_ACCEPTED for d in self.dotationprojet_set.all()
        )

    @property
    def dotation_not_treated(self) -> Optional[POSSIBLE_DOTATIONS]:
        return next(
            (
                dp.dotation
                for dp in self.dotationprojet_set.all()
                if dp.status == PROJET_STATUS_PROCESSING
            ),
            None,
        )

    @property
    def all_dotations_have_processing_status(self) -> bool:
        return all(
            dp.status == PROJET_STATUS_PROCESSING
            for dp in self.dotationprojet_set.all()
        )

    @property
    def display_notification_message(self) -> bool:
        return not self.all_dotations_have_processing_status

    @property
    def display_notification_button(self) -> bool:
        return (
            any(
                dp.status == PROJET_STATUS_ACCEPTED
                for dp in self.dotationprojet_set.all()
            )
            and self.notified_at is None
        )

    @property
    def documents(self):
        from gsl_notification.models import (
            Annexe,
            Arrete,
            ArreteEtLettreSignes,
            LettreNotification,
        )

        return sorted(
            (
                document
                for document in (
                    *Arrete.objects.filter(
                        programmation_projet__dotation_projet__projet=self
                    ),
                    *LettreNotification.objects.filter(
                        programmation_projet__dotation_projet__projet=self
                    ),
                    *ArreteEtLettreSignes.objects.filter(
                        programmation_projet__dotation_projet__projet=self
                    ),
                    *Annexe.objects.filter(
                        programmation_projet__dotation_projet__projet=self
                    ),
                )
                if document
            ),
            key=lambda d: d.created_at,
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


class DotationProjetQuerySet(models.QuerySet):
    def without_signed_document(self):
        return self.filter(
            programmation_projet__isnull=False,
            status=PROJET_STATUS_ACCEPTED,
            programmation_projet__arrete_et_lettre_signes__isnull=True,
        )


class DotationProjet(models.Model):
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE)
    dotation = models.CharField("Dotation", choices=DOTATION_CHOICES)
    # TODO pr_dotation put back protected=True, once every status transition is handled ?
    status = FSMField(
        "Statut",
        choices=PROJET_STATUS_CHOICES,
        default=PROJET_STATUS_PROCESSING,
    )
    assiette = models.DecimalField(
        "Assiette subventionnable",
        max_digits=12,
        decimal_places=2,
        null=True,
    )
    detr_avis_commission = models.BooleanField(
        "Avis commission DETR",
        help_text="Pour les projets de plus de 100 000 €",
        null=True,
    )
    detr_categories = models.ManyToManyField(
        CategorieDetr, verbose_name="Catégories d’opération DETR"
    )

    objects = DotationProjetQuerySet.as_manager()

    class Meta:
        unique_together = ("projet", "dotation")
        verbose_name = "Dotation projet"
        verbose_name_plural = "Dotations projet"

    def __str__(self):
        return f"Projet {self.projet_id} - Dotation {self.dotation}"

    def clean(self):
        errors = {}

        if self.detr_avis_commission is not None:
            if self.dotation == DOTATION_DSIL:
                errors["detr_avis_commission"] = (
                    "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
                )

            if (
                self.dossier_ds.demande_montant is not None
                and self.dossier_ds.demande_montant < MIN_DEMANDE_MONTANT_FOR_AVIS_DETR
            ):
                errors["detr_avis_commission"] = (
                    f"L'avis de la commission DETR ne doit être renseigné que pour les projets DETR dont le montant demandé est supérieur ou égal à {MIN_DEMANDE_MONTANT_FOR_AVIS_DETR}."
                )

        if (
            self.dossier_ds.finance_cout_total
            and self.assiette
            and self.dossier_ds.finance_cout_total < self.assiette
        ):
            errors["assiette"] = (
                "L'assiette ne doit pas être supérieure au coût total du projet."
            )

        if self.dotation != DOTATION_DETR:
            if self.detr_categories.exists():
                errors["detr_categories"] = (
                    "Les catégories DETR ne doivent être renseignées que pour les projets DETR."
                )
        else:
            projet_departement = (
                self.projet.perimetre.departement
                if self.projet and self.projet.perimetre
                else None
            )
            for categorie in self.detr_categories.all():
                if categorie.departement != projet_departement:
                    errors["detr_categories"] = (
                        f"La catégorie DETR « {categorie.libelle} » n'appartient pas au même département que le projet."
                    )

        if errors:
            raise ValidationError(errors)

    @property
    def dossier_ds(self):
        return self.projet.dossier_ds

    @property
    def other_dotations(self) -> List["DotationProjet"]:
        return list(d for d in self.projet.dotationprojet_set.all() if d.pk != self.pk)

    @property
    def other_accepted_dotations(self) -> List[POSSIBLE_DOTATIONS]:
        return [
            d.dotation
            for d in self.other_dotations
            if d.status == PROJET_STATUS_ACCEPTED
        ]

    @property
    def last_updated_simulation_projet(self) -> Optional["SimulationProjet"]:
        """
        We use python side sort so we benefit from prefetching !
        """
        simulations = sorted(
            self.simulationprojet_set.all(),
            key=lambda s: s.updated_at,
            reverse=True,
        )
        return simulations[0] if len(simulations) else None

    @property
    def assiette_or_cout_total(self):
        if self.assiette is not None:
            return self.assiette
        return self.dossier_ds.finance_cout_total

    @property
    def taux_de_subvention_sollicite(self) -> float | None:
        if (
            self.assiette_or_cout_total is not None
            and self.dossier_ds.demande_montant is not None
            and self.assiette_or_cout_total > 0
        ):
            return self.dossier_ds.demande_montant * 100 / self.assiette_or_cout_total
        return None

    @property
    def montant_retenu(self) -> float | None:
        if hasattr(self, "programmation_projet"):
            return self.programmation_projet.montant
        return None

    @property
    def taux_retenu(self) -> float | None:
        if hasattr(self, "programmation_projet"):
            return self.programmation_projet.taux
        return None

    @transition(field=status, source="*", target=PROJET_STATUS_ACCEPTED)
    def accept_without_ds_update(self, montant: float, enveloppe: "Enveloppe"):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_ACCEPTED,
            montant=montant,
        )

        programmation_projet, _ = ProgrammationProjet.objects.update_or_create(
            dotation_projet=self,
            enveloppe=enveloppe.delegation_root,
            defaults={
                "montant": montant,
                "status": ProgrammationProjet.STATUS_ACCEPTED,
            },
        )
        self.programmation_projet = programmation_projet

    @transaction.atomic
    @transition(field=status, source="*", target=PROJET_STATUS_ACCEPTED)
    def accept(
        self,
        montant: float,
        enveloppe: "Enveloppe",
        user: Collegue,
    ):
        self.accept_without_ds_update(montant, enveloppe)

        projet_dotation_checked = self.other_accepted_dotations
        ds_service = DsService()
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=self.projet.dossier_ds,
            user=user,
            dotations_to_be_checked=[self.dotation] + projet_dotation_checked,
            annotations_dotation_to_update=self.dotation,
            assiette=floatize(self.assiette),
            montant=floatize(montant),
            taux=floatize(self.taux_retenu),
        )

    @transition(field=status, source="*", target=PROJET_STATUS_REFUSED)
    def refuse(self, enveloppe: "Enveloppe"):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_REFUSED,
            montant=0,
        )

        ProgrammationProjet.objects.update_or_create(
            dotation_projet=self,
            enveloppe=enveloppe.delegation_root,
            defaults={
                "montant": 0,
                "status": ProgrammationProjet.STATUS_REFUSED,
            },
        )

    @transition(field=status, source="*", target=PROJET_STATUS_DISMISSED)
    def dismiss(self, enveloppe: "Enveloppe"):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_DISMISSED, montant=0
        )

        ProgrammationProjet.objects.update_or_create(
            dotation_projet=self,
            enveloppe=enveloppe.delegation_root,
            defaults={
                "montant": 0,
                "status": ProgrammationProjet.STATUS_DISMISSED,
            },
        )

    @transition(
        field=status,
        source=[PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED],
        target=PROJET_STATUS_PROCESSING,
    )
    def set_back_status_to_processing_without_ds(self):
        from gsl_programmation.models import ProgrammationProjet
        from gsl_simulation.models import SimulationProjet

        SimulationProjet.objects.filter(dotation_projet=self).update(
            status=SimulationProjet.STATUS_PROCESSING,
        )

        ProgrammationProjet.objects.filter(dotation_projet=self).delete()
        self.projet.notified_at = None
        self.projet.save()

    @transaction.atomic
    @transition(
        field=status,
        source=[PROJET_STATUS_ACCEPTED, PROJET_STATUS_REFUSED, PROJET_STATUS_DISMISSED],
        target=PROJET_STATUS_PROCESSING,
    )
    def set_back_status_to_processing(self, user: Collegue):
        self.set_back_status_to_processing_without_ds()
        ds_service = DsService()
        ds_service.update_ds_annotations_for_one_dotation(
            dossier=self.projet.dossier_ds,
            user=user,
            dotations_to_be_checked=self.other_accepted_dotations,
        )


class ProjetNote(BaseModel):
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=100)
    content = models.TextField()
    created_by = models.ForeignKey(Collegue, on_delete=models.PROTECT)


def projet_status_from_dotation_statuses(statuses: List[str] | Tuple[str]) -> str:
    from gsl_simulation.models import SimulationProjet

    if any(
        status == PROJET_STATUS_PROCESSING
        or status == SimulationProjet.STATUS_PROCESSING
        for status in statuses
    ):
        return PROJET_STATUS_PROCESSING

    if any(
        status == PROJET_STATUS_ACCEPTED or status == SimulationProjet.STATUS_ACCEPTED
        for status in statuses
    ):
        return PROJET_STATUS_ACCEPTED

    if any(
        status == PROJET_STATUS_DISMISSED or status == SimulationProjet.STATUS_DISMISSED
        for status in statuses
    ):
        return PROJET_STATUS_DISMISSED

    return PROJET_STATUS_REFUSED
