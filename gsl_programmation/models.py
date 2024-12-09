from django.db import models
from django.db.models import Q

from gsl_core.models import Arrondissement, Departement, Region


class Enveloppe(models.Model):
    TYPE_DETR = "DETR"
    TYPE_DSIL = "DSIL"
    TYPE_CHOICES = ((TYPE_DETR, TYPE_DETR), (TYPE_DSIL, TYPE_DSIL))

    type = models.CharField("Type", choices=TYPE_CHOICES)
    montant = models.DecimalField(
        "Montant",
        max_digits=14,
        decimal_places=2,
    )
    annee = models.IntegerField(verbose_name="Année")

    perimetre_region = models.ForeignKey(
        Region,
        verbose_name="Périmètre régional",
        null=True,
        on_delete=models.PROTECT,
        blank=True,
    )
    perimetre_departement = models.ForeignKey(
        Departement,
        verbose_name="Périmètre départemental",
        null=True,
        on_delete=models.PROTECT,
        blank=True,
    )
    perimetre_arrondissement = models.ForeignKey(
        Arrondissement,
        verbose_name="Périmètre d’arrondissement",
        null=True,
        on_delete=models.PROTECT,
        blank=True,
    )

    deleguee_by = models.ForeignKey(
        "self",
        verbose_name="Enveloppe déléguée",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )

    class Meta:
        constraints = (
            models.UniqueConstraint(
                name="unicity_by_perimeter_and_type",
                fields=(
                    "type",
                    "annee",
                    "perimetre_region",
                    "perimetre_departement",
                    "perimetre_arrondissement",
                ),
                nulls_distinct=False,  # important because "perimetre_*" fields are nullable
            ),
            models.CheckConstraint(
                name="only_one_perimeter",
                violation_error_message="Un seul type de périmètre doit être renseigné parmi les trois possibles.",
                condition=Q(perimetre_region__isnull=False)
                ^ Q(perimetre_departement__isnull=False)
                ^ Q(perimetre_arrondissement__isnull=False),
            ),
            models.CheckConstraint(
                condition=~Q(type="DSIL")
                | (Q(deleguee_by__isnull=True) & Q(perimetre_region__isnull=False))
                | (
                    Q(deleguee_by__isnull=False)
                    & (
                        Q(perimetre_departement__isnull=False)
                        ^ Q(perimetre_arrondissement__isnull=False)
                    )
                ),
                name="dsil_regional_perimeter",
                violation_error_message="Il faut préciser un périmètre régional pour une enveloppe de type DSIL non déléguée.",
            ),
            models.CheckConstraint(
                condition=~Q(type="DETR")
                | (Q(deleguee_by__isnull=True) & Q(perimetre_departement__isnull=False))
                | (
                    Q(deleguee_by__isnull=False)
                    & Q(perimetre_arrondissement__isnull=False)
                ),
                name="detr_departemental_perimeter",
                violation_error_message="Il faut préciser un périmètre départemental pour une enveloppe de type DETR non déléguée.",
            ),
        )

    def __str__(self):
        return f"Enveloppe {self.type} {self.annee} {self.perimetre}"

    @property
    def perimetre(self):
        return next(
            perimetre
            for perimetre in (
                self.perimetre_arrondissement,
                self.perimetre_departement,
                self.perimetre_region,
            )
            if perimetre
        )
