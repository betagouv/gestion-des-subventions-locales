import logging
from functools import cached_property
from typing import TYPE_CHECKING, List, Optional

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import (
    Case,
    Q,
    Value,
    When,
)
from django.utils import timezone
from django_fsm import FSMField, transition

from gsl.core.models import BaseModel, Collegue, Perimetre
from gsl.historique.models import ProjetAction
from gsl_demarches_simplifiees.services import DsService

from ..constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    MIN_DEMANDE_MONTANT_FOR_AVIS_DETR,
    NOTIFICATION_STATUS_NOTIFIED,
    NOTIFICATION_STATUS_TO_GENERATE,
    NOTIFICATION_STATUS_TO_NOTIFY,
    NOTIFICATION_STATUS_TO_SIGN,
    POSSIBLE_DOTATIONS,
    ProjetStatus,
)
from ..utils.utils import compute_taux, floatize

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from gsl.programmation.models import Enveloppe
    from gsl.simulation.models import SimulationProjet


class EnveloppeProjetQuerySet(models.QuerySet):
    def for_dotation(self, dotation: POSSIBLE_DOTATIONS):
        return self.filter(enveloppe__dotation=dotation)

    def programmees(self):
        return self.filter(status__in=ProjetStatus.FINAL)

    def without_signed_document(self):
        return self.programmees().filter(
            status=ProjetStatus.ACCEPTED,
            lettre_et_arrete_signes__isnull=True,
        )

    def active(self):
        return self.filter(projet__dossier_ds__is_active=True)

    def visible_to_user(self, user: Collegue):
        if user.is_staff:
            return self.all()
        return self.filter(projet__in=Projet.objects.for_user(user))

    def for_perimetre(self, perimetre: Perimetre | None):
        return self.filter(projet__in=Projet.objects.for_perimetre(perimetre))

    def to_notify(self):
        return self.filter(projet__in=Projet.objects.to_notify())

    def can_generate_accepted_documents(self):
        return self.programmees().filter(
            status=ProjetStatus.ACCEPTED,
            projet__notified_at__isnull=True,
        )

    def can_generate_refus_documents(self):
        return self.programmees().filter(
            status__in=ProjetStatus.NEGATIVE,
            projet__notified_at__isnull=True,
        )

    def annotate_notification_status(self):
        return self.annotate(
            _notification_status=Case(
                When(status=ProjetStatus.PROCESSING, then=Value(None)),
                When(
                    projet__notified_at__isnull=False,
                    then=Value(NOTIFICATION_STATUS_NOTIFIED),
                ),
                When(
                    Q(lettre_et_arrete_signes__isnull=False)
                    | Q(lettre_refus_signee__isnull=False),
                    then=Value(NOTIFICATION_STATUS_TO_NOTIFY),
                ),
                When(
                    status=ProjetStatus.ACCEPTED,
                    arrete__isnull=False,
                    lettrenotification__isnull=False,
                    then=Value(NOTIFICATION_STATUS_TO_SIGN),
                ),
                When(
                    status__in=ProjetStatus.NEGATIVE,
                    lettrerefus__isnull=False,
                    then=Value(NOTIFICATION_STATUS_TO_SIGN),
                ),
                default=Value(NOTIFICATION_STATUS_TO_GENERATE),
                output_field=models.CharField(null=True),
            )
        )


class EnveloppeProjetManager(models.Manager.from_queryset(EnveloppeProjetQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related("enveloppe")

    def create_for(
        self, projet: "Projet", enveloppe: "Enveloppe", **kwargs
    ) -> "EnveloppeProjet":
        return self.create(
            projet=projet,
            enveloppe=enveloppe,
            detr_avis_commission=projet.dossier_ds.detr_avis_commission_for(
                enveloppe.dotation
            ),
            **kwargs,
        )


class EnveloppeProjetCourantManager(EnveloppeProjetManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_courant=True)


class EnveloppeProjet(BaseModel):
    projet = models.ForeignKey("gsl_projet.Projet", on_delete=models.CASCADE)
    # TODO pr_dotation put back protected=True, once every status transition is handled ?
    status = FSMField(
        "Statut",
        choices=ProjetStatus,
        default=ProjetStatus.PROCESSING,
    )
    assiette = models.DecimalField(
        "Assiette subventionnable",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
    )
    detr_avis_commission = models.BooleanField(
        "Avis commission DETR",
        help_text="Pour les projets de plus de 100 000 €",
        null=True,
    )
    enveloppe = models.ForeignKey(
        "gsl_programmation.Enveloppe",
        verbose_name="Enveloppe",
        on_delete=models.PROTECT,
    )
    montant = models.DecimalField(
        "Montant", max_digits=14, decimal_places=2, blank=True, null=True
    )
    date_programmation = models.DateTimeField(
        "Date de programmation", blank=True, null=True
    )
    is_courant = models.BooleanField("Courant", default=True)

    objects = EnveloppeProjetCourantManager()
    all_objects = EnveloppeProjetManager()

    class Meta:
        default_manager_name = "objects"
        verbose_name = "Enveloppe projet"
        verbose_name_plural = "Enveloppes projet"
        constraints = (
            models.UniqueConstraint(
                fields=("projet", "enveloppe"),
                condition=Q(is_courant=True),
                name="un_seul_enveloppe_projet_courant_par_enveloppe",
                violation_error_message="Ce projet a déjà un enveloppe projet courant "
                "sur cette enveloppe.",
            ),
            models.CheckConstraint(
                condition=Q(
                    status=ProjetStatus.PROCESSING,
                    montant__isnull=True,
                    date_programmation__isnull=True,
                )
                | Q(
                    status=ProjetStatus.ACCEPTED,
                    montant__isnull=False,
                    date_programmation__isnull=False,
                )
                | Q(
                    status__in=ProjetStatus.NEGATIVE,
                    montant__isnull=True,
                    date_programmation__isnull=False,
                ),
                name="montant_et_date_selon_statut",
                violation_error_message="Une dotation en traitement ne porte ni montant "
                "ni date de programmation, une dotation acceptée porte les deux, et une "
                "dotation refusée ou classée sans suite porte une date de programmation "
                "mais pas de montant.",
            ),
        )

    def __str__(self):
        return f"Projet {self.projet_id} - Dotation {self.dotation}"

    def clean_fields(self, exclude=None):
        try:
            super().clean_fields(exclude=exclude)
        except ValidationError as e:
            errors = e.update_error_dict({})
        else:
            errors = {}

        if "detr_avis_commission" not in exclude:
            self._validate_detr_avis_commission(errors)

        if "assiette" not in exclude:
            if (
                self.dossier_ds.finance_cout_total
                and self.assiette
                and self.dossier_ds.finance_cout_total < self.assiette
            ):
                errors["assiette"] = (
                    "L'assiette doit être inférieure ou égale au coût total du projet."
                )

        if errors:
            raise ValidationError(errors)

    def clean(self):
        super().clean()

        errors = {}
        self._validate_montant(errors)
        self._validate_enveloppe(errors)
        if errors:
            raise ValidationError(errors)

    def _validate_montant(self, errors):
        if self.status in ProjetStatus.NEGATIVE:
            if self.montant is not None:
                errors["montant"] = [
                    "Un projet refusé ou classé sans suite ne doit pas porter de montant."
                ]
            return

        if not self.montant:
            return

        if self.assiette is not None:
            if self.montant > self.assiette:
                errors["montant"] = [
                    "Le montant de la programmation ne peut pas être supérieur à l'assiette du projet pour cette dotation."
                ]
        elif (
            self.dossier_ds.finance_cout_total
            and self.montant > self.dossier_ds.finance_cout_total
        ):
            errors["montant"] = [
                "Le montant de la programmation ne peut pas être supérieur au coût total du projet pour cette dotation."
            ]

    def _validate_enveloppe(self, errors):
        if self.enveloppe.is_deleguee:
            errors["enveloppe"] = [
                "Une programmation ne peut pas être faite sur une enveloppe déléguée."
                "Il faut programmer sur l'enveloppe mère."
            ]

        if not self.enveloppe.perimetre.contains_or_equal(self.projet.perimetre):
            errors["enveloppe"] = [
                "Le périmètre de l'enveloppe ne contient pas le périmètre du projet."
            ]

    def _validate_detr_avis_commission(self, errors):
        if self.detr_avis_commission is None:
            return

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

    def save(self, *args, **kwargs):
        if self._state.adding and self.assiette is None:
            dossier = self.dossier_ds
            annotation_assiette = dossier.annotations_for(self.dotation).assiette
            self.assiette = (
                annotation_assiette
                if annotation_assiette is not None
                else dossier.finance_cout_total
            )
        super().save(*args, **kwargs)

    @property
    def dotation(self) -> POSSIBLE_DOTATIONS:
        return self.enveloppe.dotation

    @property
    def dossier_ds(self):
        return self.projet.dossier_ds

    @property
    def is_programmee(self) -> bool:
        return self.status in ProjetStatus.FINAL

    @property
    def is_programmee_after_passage_en_instruction(self) -> bool:
        return (
            self.is_programmee
            and self.date_programmation > self.dossier_ds.ds_date_passage_en_instruction
        )

    @property
    def other_dotations(self) -> List["EnveloppeProjet"]:
        return list(d for d in self.projet.enveloppeprojet_set.all() if d.pk != self.pk)

    @property
    def other_accepted_dotations(self) -> List[POSSIBLE_DOTATIONS]:
        return [
            d.dotation
            for d in self.other_dotations
            if d.status == ProjetStatus.ACCEPTED
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

    def compute_montant_from_taux(self, new_taux):
        from decimal import Decimal, InvalidOperation

        try:
            assiette = self.assiette_or_cout_total
            new_montant = (assiette * Decimal(new_taux) / 100) if assiette else 0
            new_montant = round(new_montant, 2)
            return max(min(new_montant, self.assiette_or_cout_total), 0)
        except TypeError:
            return 0
        except InvalidOperation:
            return 0

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
        return self.montant

    @property
    def taux_retenu(self) -> float | None:
        if self.montant is None:
            return None
        return compute_taux(self.montant, self.assiette_or_cout_total)

    @property
    def notification_status(self) -> str | None:
        if hasattr(self, "_notification_status"):
            return self._notification_status

        return (
            EnveloppeProjet.objects.annotate_notification_status()
            .values_list("_notification_status", flat=True)
            .get(pk=self.pk)
        )

    @property
    def is_treated(self) -> bool:
        return self.is_programmee

    @property
    def lettre(self):
        """Bridge between the LETTRE document_type and the related_name, so
        `getattr(enveloppe_projet, document_type)` resolves for every type."""
        return self.lettrenotification

    @property
    def refus(self):
        return self.lettrerefus

    @cached_property
    def documents_summary(self):
        summary = list()

        if hasattr(self, "lettre_et_arrete_signes"):
            summary.append("1 lettre et arrêté signés")
        else:
            if hasattr(self, "arrete"):
                summary.append("1 arrêté")
            if hasattr(self, "lettrenotification"):
                summary.append("1 lettre")

        if hasattr(self, "lettre_refus_signee"):
            summary.append("1 lettre de refus signée")
        elif hasattr(self, "lettrerefus"):
            summary.append("1 lettre de refus")

        annexes_count = len(self.annexes.all())
        if annexes_count != 0:
            plural = "s" if annexes_count > 1 else ""
            summary.append(f"{annexes_count} annexe{plural}")

        return summary

    @transition(field=status, source="*", target=ProjetStatus.ACCEPTED)
    def accept_without_ds_update(
        self, montant: float, enveloppe: "Enveloppe", actor=None
    ):
        from gsl.simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        status_is_changing = self.status != ProjetStatus.ACCEPTED
        previous_enveloppe = self.enveloppe
        previous_montant = self.montant

        SimulationProjet.objects.filter(enveloppe_projet=self).update(
            status=SimulationProjet.STATUS_ACCEPTED,
            montant=montant,
        )

        self.enveloppe = enveloppe.delegation_root
        self.montant = montant
        if self.date_programmation is None:
            self.date_programmation = timezone.now()

        source, created_at = self._status_change_source_and_created_at(actor)
        if status_is_changing or previous_enveloppe != enveloppe.delegation_root:
            ProjetAction.objects.create(
                projet=self.projet,
                action_type=ProjetAction.TYPE_STATUS_CHANGE,
                actor=actor,
                source=source,
                created_at=created_at,
                dotation=self.dotation,
                status=ProjetStatus.ACCEPTED,
                euro_field_value=montant,
                enveloppe=enveloppe,
            )
        elif previous_montant is not None and previous_montant != montant:
            ProjetAction.objects.create(
                projet=self.projet,
                action_type=ProjetAction.TYPE_MONTANT_MODIFIED,
                actor=actor,
                source=source,
                created_at=created_at,
                dotation=self.dotation,
                euro_field_value=montant,
            )

    @transaction.atomic
    @transition(field=status, source="*", target=ProjetStatus.ACCEPTED)
    def accept(
        self,
        montant: float,
        enveloppe: "Enveloppe",
        user: Collegue,
    ):
        self.accept_without_ds_update(montant, enveloppe, actor=user)

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

    @transition(field=status, source="*", target=ProjetStatus.REFUSED)
    def refuse(self, enveloppe: "Enveloppe", actor=None):
        from gsl.simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        SimulationProjet.objects.filter(enveloppe_projet=self).update(
            status=SimulationProjet.STATUS_REFUSED,
            montant=0,
        )

        self.enveloppe = enveloppe.delegation_root
        self.montant = None
        if self.date_programmation is None:
            self.date_programmation = timezone.now()

        source, created_at = self._status_change_source_and_created_at(actor)

        ProjetAction.objects.create(
            projet=self.projet,
            action_type=ProjetAction.TYPE_STATUS_CHANGE,
            actor=actor,
            source=source,
            created_at=created_at,
            dotation=self.dotation,
            status=ProjetStatus.REFUSED,
            enveloppe=enveloppe,
        )

    @transition(field=status, source="*", target=ProjetStatus.DISMISSED)
    def dismiss(self, enveloppe: "Enveloppe", actor=None):
        from gsl.simulation.models import SimulationProjet

        if self.dotation != enveloppe.dotation:
            raise ValidationError(
                "La dotation du projet et de l'enveloppe ne correspondent pas."
            )

        SimulationProjet.objects.filter(enveloppe_projet=self).update(
            status=SimulationProjet.STATUS_DISMISSED, montant=0
        )

        self.enveloppe = enveloppe.delegation_root
        self.montant = None
        if self.date_programmation is None:
            self.date_programmation = timezone.now()

        source, created_at = self._status_change_source_and_created_at(actor)
        ProjetAction.objects.create(
            projet=self.projet,
            action_type=ProjetAction.TYPE_STATUS_CHANGE,
            actor=actor,
            source=source,
            created_at=created_at,
            dotation=self.dotation,
            status=ProjetStatus.DISMISSED,
            enveloppe=enveloppe,
        )

    def _status_change_source_and_created_at(self, actor=None):
        """
        Compute the `source` and `created_at` to use for the `ProjetAction`
        recorded by a status transition (accept/refuse/dismiss).

        When there is no `actor`, the change comes from a Démarches
        Numériques sync rather than a Turgot user, so the action is
        backdated to the DS processing date when we know it.
        """
        created_at = timezone.now()

        if actor is not None:
            return ProjetAction.SOURCE_TURGOT, created_at

        if self.dossier_ds.ds_date_traitement:
            created_at = self.dossier_ds.ds_date_traitement
        return ProjetAction.SOURCE_DN, created_at

    @transition(
        field=status,
        source=ProjetStatus.FINAL,
        target=ProjetStatus.PROCESSING,
    )
    def set_back_status_to_processing_without_ds(self, actor=None):
        from gsl.simulation.models import SimulationProjet

        SimulationProjet.objects.filter(enveloppe_projet=self).update(
            status=SimulationProjet.STATUS_PROCESSING,
        )

        self.montant = None
        self.date_programmation = None
        self.projet.notified_at = None
        self.projet.save()

        ProjetAction.objects.create(
            projet=self.projet,
            action_type=ProjetAction.TYPE_STATUS_CHANGE,
            actor=actor,
            source=ProjetAction.SOURCE_TURGOT
            if actor is not None
            else ProjetAction.SOURCE_DN,
            dotation=self.dotation,
            status=ProjetStatus.PROCESSING,
        )

    @transaction.atomic
    @transition(
        field=status,
        source=ProjetStatus.FINAL,
        target=ProjetStatus.PROCESSING,
    )
    def set_back_status_to_processing(self, user: Collegue):
        is_notified = self.projet.has_been_notified
        ds_service = DsService()

        self.set_back_status_to_processing_without_ds(actor=user)

        if is_notified:
            ds_service.repasser_en_instruction(self.projet.dossier_ds, user)

        ds_service.update_ds_annotations_for_one_dotation(
            dossier=self.projet.dossier_ds,
            user=user,
            dotations_to_be_checked=self.other_accepted_dotations,
        )

    ## -------------------------- Following DN --------------------------

    @property
    def programmation_root_enveloppe(self) -> "Enveloppe":
        """A treatment coming from DN carries no campagne, so a dotation programmed
        from it lands on the year of its treatment date, not of its deposit."""
        return self.projet.root_enveloppe(
            self.dotation, self.dossier_ds.annee_de_traitement
        )

    def accept_from_dn(self) -> None:
        if self.dotation == DOTATION_DETR:
            self.detr_avis_commission = True

        # We keep the previous enveloppe to avoid squashing a manual rectification.
        enveloppe = (
            self.enveloppe if self.is_programmee else self.programmation_root_enveloppe
        )
        self.accept_without_ds_update(
            montant=self._montant_from_dn(), enveloppe=enveloppe
        )
        self.save()

    def _montant_from_dn(self):
        montant = self.dossier_ds.annotations_for(self.dotation).montant
        if montant is None:
            logger.warning(
                "Montant is missing in dossier annotations",
                extra={
                    "dossier_ds_number": self.dossier_ds.ds_number,
                    "dotation": self.dotation,
                },
            )
            return 0
        return montant

    def close_from_dn(self, transition_method) -> None:
        transition_method(self, enveloppe=self.programmation_root_enveloppe)
        self.save()

    def update_montant_from_dn(self) -> None:
        montant = self.dossier_ds.annotations_for(self.dotation).montant
        if montant is None or montant == self.montant:
            return
        self.accept_without_ds_update(montant=montant, enveloppe=self.enveloppe)
        self.save()

    def update_assiette_from_dn(self) -> None:
        assiette = self.dossier_ds.annotations_for(self.dotation).assiette
        if assiette is None:
            return

        if self.assiette != assiette:
            ProjetAction.objects.create(
                projet=self.projet,
                action_type=ProjetAction.TYPE_ASSIETTE_MODIFIED,
                actor=None,
                source=ProjetAction.SOURCE_DN,
                dotation=self.dotation,
                euro_field_value=assiette,
            )

        self.assiette = assiette
        self.save()


# Imported last: projet.py imports this module at load time.
from .projet import Projet  # noqa: E402
