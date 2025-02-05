from django.core.exceptions import ValidationError
from django.db import models

from gsl_core.models import Perimetre


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
    perimetre = models.ForeignKey(
        Perimetre, on_delete=models.PROTECT, verbose_name="Périmètre", null=True
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
                    "annee",
                    "type",
                    "perimetre",
                ),
            ),
        )

    def __str__(self):
        return f"Enveloppe {self.type} {self.annee} {self.perimetre}"

    @property
    def is_deleguee(self):
        return self.deleguee_by is not None

    def clean(self):
        if self.type == self.TYPE_DETR:  # scope "département"
            if not self.is_deleguee and (
                self.perimetre.arrondissement is not None
                or self.perimetre.departement is None
            ):
                raise ValidationError(
                    "Il faut préciser un périmètre départemental pour une enveloppe de type DETR non déléguée."
                )
        if self.type == self.TYPE_DSIL:
            if not self.is_deleguee and self.perimetre.departement is not None:
                raise ValidationError(
                    "Il faut préciser un périmètre régional pour une enveloppe de type DSIL non déléguée."
                )
        if self.is_deleguee and not self.deleguee_by.perimetre.contains(self.perimetre):
            raise ValidationError(
                "Le périmètre de l'enveloppe délégante est incohérent avec celui de l'enveloppe déléguée."
            )
