from functools import cached_property

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Sum

from gsl.projet.constants import (
    DOTATION_CHOICES,
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_REFUSED,
)
from gsl.projet.models import DotationProjet, Projet
from gsl_core.models import BaseModel, Perimetre


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
            new_obj.deleguee_by is not None
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

        new_obj.deleguee_by = self.model.objects.get_or_create(
            dotation=new_obj.dotation,
            annee=new_obj.annee,
            perimetre=new_obj.perimetre.parent,
            defaults={"montant": new_obj.montant},
        )[0]
        new_obj.save(update_fields=["deleguee_by"])
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

    deleguee_by = models.ForeignKey(
        "self",
        verbose_name="Enveloppe déléguée",
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
        return self.deleguee_by is not None

    @property
    def ordered_sous_enveloppes(self):
        return self.enveloppe_set.order_by(
            "perimetre__departement_id", "perimetre__arrondissement_id"
        )

    @property
    def delegation_root(self) -> "Enveloppe":
        if not self.is_deleguee:
            return self
        else:
            return self.deleguee_by.delegation_root

    @cached_property
    def enveloppe_projets_included(self):
        return Projet.objects.active().included_in_enveloppe(self)

    @property
    def montant_asked(self):
        return self.enveloppe_projets_included.aggregate(
            Sum("dossier_ds__demande_montant")
        )["dossier_ds__demande_montant__sum"]

    @cached_property
    def enveloppe_projets_processed(self):
        if self.is_deleguee:
            return DotationProjet.objects.active().filter(
                enveloppe=self.delegation_root,
                projet__in=self.enveloppe_projets_included,
            )
        return DotationProjet.objects.active().filter(enveloppe=self)

    @property
    def accepted_montant(self):
        return (
            self.enveloppe_projets_processed.filter(
                status=PROJET_STATUS_ACCEPTED
            ).aggregate(Sum("montant"))["montant__sum"]
            or 0
        )

    @property
    def reste_a_attribuer(self):
        return self.montant - self.accepted_montant

    @property
    def validated_projets_count(self):
        return self.enveloppe_projets_processed.filter(
            status=PROJET_STATUS_ACCEPTED
        ).count()

    @property
    def refused_projets_count(self):
        return self.enveloppe_projets_processed.filter(
            status=PROJET_STATUS_REFUSED
        ).count()

    @property
    def demandeurs_count(self):
        return self.enveloppe_projets_included.aggregate(
            count=models.Count("dossier_ds__ds_demandeur", distinct=True)
        )["count"]

    @property
    def projets_count(self):
        return self.enveloppe_projets_included.count()

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

        if self.is_deleguee and not self.deleguee_by.perimetre.contains(self.perimetre):
            raise ValidationError(
                "Le périmètre de l'enveloppe délégante est incohérent avec celui de l'enveloppe déléguée."
            )
