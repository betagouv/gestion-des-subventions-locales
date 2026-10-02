import logging
from datetime import date
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Count, QuerySet, Sum
from django.forms import ValidationError
from django_extensions.db.fields import AutoSlugField

from gsl.core.models import BaseModel, Collegue, Perimetre
from gsl.programmation.models import Enveloppe
from gsl.programmation.services.enveloppe_service import EnveloppeService
from gsl.projet.constants import DOTATION_DETR, DOTATION_DSIL, ProjetStatus
from gsl.projet.models import EnveloppeProjet, Projet
from gsl.projet.utils.utils import compute_taux

logger = logging.getLogger(__name__)


def validate_columns_visibility(value):
    from .table_columns import SIMULATION_TABLE_COLUMNS

    if not isinstance(value, dict):
        raise ValidationError("La valeur doit être un objet JSON.")
    valid_keys = {col.css_key for col in SIMULATION_TABLE_COLUMNS if col.hideable}
    for key, val in value.items():
        if key not in valid_keys:
            raise ValidationError(f"Clé de colonne inconnue : {key}")
        if not isinstance(val, bool):
            raise ValidationError(f"La valeur pour '{key}' doit être un booléen.")


class SimulationQuerySet(models.QuerySet):
    def containing_perimetre(self, perimetre: Perimetre):
        ancestors_qs = perimetre.ancestors()
        perimetres_to_filter = list(ancestors_qs) + [perimetre]
        return self.filter(enveloppe__perimetre__in=perimetres_to_filter)

    def for_enveloppe_projet(self, enveloppe_projet: EnveloppeProjet):
        dossier = enveloppe_projet.dossier_ds
        qs = self.containing_perimetre(enveloppe_projet.projet.perimetre).filter(
            enveloppe__dotation=enveloppe_projet.dotation,
            enveloppe__annee__gte=date.today().year,
        )
        # TODO Investigate why we need those two checks
        if dossier.is_treated and dossier.ds_date_traitement is not None:
            qs = qs.filter(enveloppe__annee__lte=dossier.annee_de_traitement)
        if enveloppe_projet.is_programmee:
            qs = qs.filter(enveloppe__annee__lte=enveloppe_projet.enveloppe.annee)
        return qs

    def visible_for_user(self, user: Collegue):
        return self.filter(
            enveloppe__in=EnveloppeService.get_enveloppes_visible_for_a_user(user)
        )


class SimulationManager(models.Manager.from_queryset(SimulationQuerySet)):
    pass


class Simulation(BaseModel):
    title = models.CharField(verbose_name="Titre")
    created_by = models.ForeignKey(Collegue, on_delete=models.SET_NULL, null=True)
    enveloppe = models.ForeignKey(
        Enveloppe,
        on_delete=models.PROTECT,
        verbose_name="Enveloppe de dotation associée",
    )
    slug = AutoSlugField(
        verbose_name="Clé d’URL",
        unique=True,
        max_length=120,
        populate_from="title",
        blank=False,
    )
    columns_visibility = models.JSONField(
        verbose_name="Colonnes affichées",
        null=True,
        blank=True,
        default=None,
        validators=[validate_columns_visibility],
    )
    filters = models.JSONField(
        verbose_name="Filtres appliqués",
        null=True,
        blank=True,
        default=None,
    )
    downloaded_at = models.DateTimeField(
        verbose_name="Date de téléchargement",
        null=True,
        blank=True,
        default=None,
    )

    objects = SimulationManager()

    class Meta:
        verbose_name = "Simulation"
        verbose_name_plural = "Simulations"

    def __str__(self):
        return self.title

    @property
    def dotation(self):
        return self.enveloppe.dotation

    def get_absolute_url(self):
        from django.urls import reverse

        if not self.slug:
            return reverse("simulation:simulation-form")

        return reverse("simulation:simulation-detail", kwargs={"slug": self.slug})

    def get_projet_status_summary(self):
        default_status_summary = {
            SimulationProjet.STATUS_PROCESSING: 0,
            SimulationProjet.STATUS_ACCEPTED: 0,
            SimulationProjet.STATUS_REFUSED: 0,
            SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: 0,
            SimulationProjet.STATUS_PROVISIONALLY_REFUSED: 0,
            "notified": 0,
        }
        status_count = (
            SimulationProjet.objects.active()
            .filter(simulation=self)
            .values("status")
            .annotate(count=Count("status"))
        )

        summary = {item["status"]: item["count"] for item in status_count}

        notified_count = (
            SimulationProjet.objects.active()
            .filter(
                simulation=self,
                enveloppe_projet__projet__notified_at__isnull=False,
            )
            .count()
        )

        return {**default_status_summary, **summary, "notified": notified_count}

    def get_total_amount_granted(self, qs: QuerySet[Projet]):
        statuses_to_include = (
            SimulationProjet.STATUS_ACCEPTED,
            SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        )
        return (
            qs.filter(
                enveloppeprojet__simulationprojet__simulation=self,
                enveloppeprojet__simulationprojet__status__in=statuses_to_include,
            ).aggregate(Sum("enveloppeprojet__simulationprojet__montant"))[
                "enveloppeprojet__simulationprojet__montant__sum"
            ]
            or 0.0
        )


class SimulationProjetQuerySet(models.QuerySet):
    def active(self):
        return self.filter(enveloppe_projet__projet__dossier_ds__is_active=True)

    def in_user_perimeter(self, user: Collegue):
        if user.is_staff:
            return self.all()
        return self.filter(
            simulation__enveloppe__in=EnveloppeService.get_enveloppes_visible_for_a_user(
                user
            )
        )


class SimulationProjetManager(models.Manager.from_queryset(SimulationProjetQuerySet)):
    def reset_for_enveloppe_projet(self, enveloppe_projet: EnveloppeProjet) -> None:
        concerned = Simulation.objects.for_enveloppe_projet(enveloppe_projet)
        self.filter(enveloppe_projet=enveloppe_projet).exclude(
            simulation__in=concerned
        ).delete()
        for simulation in concerned.exclude(
            simulationprojet__enveloppe_projet=enveloppe_projet
        ):
            self.create_or_update_for(enveloppe_projet, simulation)

    def create_or_update_for(
        self, enveloppe_projet: EnveloppeProjet, simulation: Simulation
    ) -> "SimulationProjet":
        status = self.status_for(enveloppe_projet)
        simulation_projet, _ = self.update_or_create(
            enveloppe_projet=enveloppe_projet,
            simulation=simulation,
            defaults={
                "montant": self.initial_montant_for(enveloppe_projet, status),
                "status": status,
            },
        )
        return simulation_projet

    def status_for(self, enveloppe_projet: EnveloppeProjet) -> str:
        return self.model.STATUS_FROM_PROJET_STATUS.get(enveloppe_projet.status)

    def initial_montant_for(
        self, enveloppe_projet: EnveloppeProjet, status: str
    ) -> Decimal:
        if status in (self.model.STATUS_DISMISSED, self.model.STATUS_REFUSED):
            return Decimal(0)

        if enveloppe_projet.montant is not None:
            return enveloppe_projet.montant

        dossier = enveloppe_projet.projet.dossier_ds

        if enveloppe_projet.dotation == DOTATION_DETR:
            dossier_montant_annotations = dossier.annotations_montant_accorde_detr
        elif enveloppe_projet.dotation == DOTATION_DSIL:
            dossier_montant_annotations = dossier.annotations_montant_accorde_dsil

        if dossier_montant_annotations:
            return self._capped_by_assiette_or_cout_total(
                dossier_montant_annotations,
                enveloppe_projet,
                "le montant accordé issu des annotations",
            )

        if dossier.demande_montant:
            return self._capped_by_assiette_or_cout_total(
                dossier.demande_montant,
                enveloppe_projet,
                "le montant demandé",
            )

        return Decimal(0)

    def _capped_by_assiette_or_cout_total(
        self, value: Decimal, enveloppe_projet: EnveloppeProjet, value_label: str
    ) -> Decimal:
        if enveloppe_projet.assiette_or_cout_total is None:
            logger.warning(
                f"Le projet de dotation {enveloppe_projet.dotation} (id: {enveloppe_projet.pk}) n'a ni assiette ni coût total."
            )
            return value

        if value and value > enveloppe_projet.assiette_or_cout_total:
            logger.warning(
                f"Le projet de dotation {enveloppe_projet.dotation} (id: {enveloppe_projet.pk}) a une assiette plus petite que {value_label}."
            )

        return min(value, enveloppe_projet.assiette_or_cout_total)


class SimulationProjet(BaseModel):
    STATUS_PROCESSING = "draft"
    STATUS_ACCEPTED = "valid"
    STATUS_REFUSED = "cancelled"
    STATUS_PROVISIONALLY_ACCEPTED = "provisionally_accepted"
    STATUS_PROVISIONALLY_REFUSED = "provisionally_refused"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = (
        (STATUS_PROCESSING, "🔄 En traitement"),
        (STATUS_ACCEPTED, "✅ Accepté"),
        (STATUS_PROVISIONALLY_ACCEPTED, "✔️ Accepté provisoirement"),
        (STATUS_PROVISIONALLY_REFUSED, "✖️ Refusé provisoirement"),
        (STATUS_REFUSED, "❌ Refusé"),
        (STATUS_DISMISSED, "⛔️ Classé sans suite"),
    )

    SIMULATION_PENDING_STATUSES = (
        STATUS_PROCESSING,
        STATUS_PROVISIONALLY_ACCEPTED,
        STATUS_PROVISIONALLY_REFUSED,
    )

    STATUS_FROM_PROJET_STATUS = {
        ProjetStatus.ACCEPTED: STATUS_ACCEPTED,
        ProjetStatus.DISMISSED: STATUS_DISMISSED,
        ProjetStatus.REFUSED: STATUS_REFUSED,
        ProjetStatus.PROCESSING: STATUS_PROCESSING,
    }

    enveloppe_projet = models.ForeignKey(
        EnveloppeProjet, on_delete=models.CASCADE, null=True
    )
    simulation = models.ForeignKey(
        Simulation, on_delete=models.CASCADE, null=True, blank=True
    )

    montant = models.DecimalField(
        decimal_places=2,
        max_digits=14,
        validators=[MinValueValidator(0)],
        verbose_name="Montant",
    )
    status = models.CharField(
        verbose_name="État", choices=STATUS_CHOICES, default=STATUS_PROCESSING
    )

    objects = SimulationProjetManager()

    class Meta:
        verbose_name = "Projet de simulation"
        verbose_name_plural = "Projets de simulation"
        constraints = (
            models.UniqueConstraint(
                fields=("enveloppe_projet", "simulation"),
                name="unique_projet_simulation",
                nulls_distinct=True,
            ),
        )

    def __str__(self):
        return f"Simulation projet {self.pk}"

    @property
    def projet(self):
        return self.enveloppe_projet.projet

    @property
    def dossier(self):
        return self.projet.dossier_ds

    @property
    def enveloppe(self):
        return self.simulation.enveloppe

    @property
    def dotation(self):
        return self.enveloppe_projet.dotation

    @property
    def taux(self):
        return compute_taux(self.montant, self.enveloppe_projet.assiette_or_cout_total)

    def clean(self):
        errors = []

        if self.status not in self.SIMULATION_PENDING_STATUSES:
            self._validate_montant(errors)
        self._validate_dotation(errors)
        if errors:
            raise ValidationError(errors)

    def _validate_montant(self, errors):
        if self.enveloppe_projet.assiette is not None:
            if self.montant and self.montant > self.enveloppe_projet.assiette:
                errors.append(
                    "Le montant doit être inférieur ou égal à l'assiette du projet pour cette dotation."
                )
        else:
            if (
                self.montant
                and self.projet.dossier_ds.finance_cout_total
                and self.montant > self.projet.dossier_ds.finance_cout_total
            ):
                errors.append(
                    "Le montant doit être inférieur ou égal au coût total du projet."
                )

    def _validate_dotation(self, errors):
        if self.enveloppe_projet.dotation != self.simulation.enveloppe.dotation:
            errors.append(
                "La dotation du projet doit être la même que la dotation de la simulation."
            )


# BulkActionsJob.action of a bulk SimulationProjet status change
BULK_STATUS_ACTION = "simulation_status"
