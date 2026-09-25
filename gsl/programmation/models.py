from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

from gsl.core.models import BaseModel, Perimetre
from gsl.projet.constants import (
    DOTATION_CHOICES,
    DOTATION_DETR,
    DOTATION_DSIL,
)


class EnveloppeQueryset(models.QuerySet):
    @transaction.atomic
    def create(
        self, dotation: str | None = None, perimetre: Perimetre | None = None, **kwargs
    ):
        # Business constraints (there for safety but should never raise, we have form validation)
        if dotation == DOTATION_DETR and perimetre.type == Perimetre.TYPE_REGION:
            raise ValueError("For a DETR Enveloppe, region perimeter is not allowed")

        new_obj = super().create(dotation=dotation, perimetre=perimetre, **kwargs)
        if (
            new_obj.is_deleguee
            or (
                new_obj.dotation == DOTATION_DETR
                and new_obj.perimetre.arrondissement is None
            )
            or (
                new_obj.dotation == DOTATION_DSIL
                and new_obj.perimetre.departement is None
            )
        ):
            return new_obj

        new_obj.parent = self.model.objects.get_or_create(
            dotation=new_obj.dotation,
            annee=new_obj.annee,
            perimetre=new_obj.perimetre.parent,
            defaults={"montant": new_obj.montant},
        )[0]
        new_obj.save(update_fields=["parent"])
        return new_obj

    def for_current_year(self):
        return self.filter(annee=self.values("annee").order_by("-annee")[:1])


class EnveloppeManager(models.Manager.from_queryset(EnveloppeQueryset)):
    pass


class Enveloppe(BaseModel):
    dotation = models.CharField("Dotation", choices=DOTATION_CHOICES)
    montant = models.DecimalField(
        "Montant",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    annee = models.IntegerField(verbose_name="Année")
    perimetre = models.ForeignKey(
        Perimetre, on_delete=models.PROTECT, verbose_name="Périmètre"
    )

    parent = models.ForeignKey(
        "self",
        verbose_name="Enveloppe parente",
        null=True,
        on_delete=models.PROTECT,
        blank=True,
    )

    objects = EnveloppeManager()

    class Meta:
        constraints = (
            models.UniqueConstraint(
                name="unicity_by_perimeter_and_dotation",
                violation_error_message="Cette enveloppe est déjà programmée pour ce territoire et cette dotation.",
                fields=(
                    "annee",
                    "dotation",
                    "perimetre",
                ),
            ),
        )

    def __str__(self):
        return f"Enveloppe {self.dotation} {self.annee} {self.perimetre}"

    @property
    def is_deleguee(self):
        return self.parent_id is not None

    @property
    def ordered_sous_enveloppes(self):
        return self.enveloppe_set.order_by(
            "perimetre__departement_id", "perimetre__arrondissement_id"
        )

    @property
    def delegation_root(self) -> "Enveloppe":
        if self.is_deleguee:
            return self.parent.delegation_root
        return self

    @property
    def is_arrondissement(self):
        return self.perimetre.type == Perimetre.TYPE_ARRONDISSEMENT

    def clean(self):
        if self.dotation == DOTATION_DETR:  # scope "département"
            if self.perimetre.type == Perimetre.TYPE_REGION:
                raise ValidationError(
                    "Une enveloppe DETR ne peut pas avoir un périmètre régional."
                )

            if self.perimetre.type == Perimetre.TYPE_DEPARTEMENT and self.is_deleguee:
                raise ValidationError(
                    "Une enveloppe DETR déléguée ne peut pas être une enveloppe départementale."
                )

            if (
                self.perimetre.type == Perimetre.TYPE_ARRONDISSEMENT
                and not self.is_deleguee
            ):
                raise ValidationError(
                    "Une enveloppe DETR et de périmètre arrondissement doit obligatoirement être déléguée."
                )

        if self.dotation == DOTATION_DSIL:
            if self.is_deleguee and self.perimetre.type == Perimetre.TYPE_REGION:
                raise ValidationError(
                    "Une enveloppe DSIL déléguée ne peut pas être une enveloppe régionale."
                )
            if not self.is_deleguee and self.perimetre.type != Perimetre.TYPE_REGION:
                raise ValidationError(
                    "Il faut préciser un périmètre régional pour une enveloppe DSIL non déléguée."
                )

        if self.is_deleguee and not self.parent.perimetre.contains(self.perimetre):
            raise ValidationError(
                "Le périmètre de l'enveloppe délégante est incohérent avec celui de l'enveloppe déléguée."
            )
