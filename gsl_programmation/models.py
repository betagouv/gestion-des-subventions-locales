from functools import cached_property

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from typing_extensions import deprecated

from gsl_core.models import Perimetre
from gsl_projet.constants import DOTATION_CHOICES, DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet, Projet
from gsl_projet.utils.utils import compute_taux


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
        return self.filter(
            annee=self.order_by("-annee").values_list("annee", flat=True).first()
        )


class EnveloppeManager(models.Manager.from_queryset(EnveloppeQueryset)):
    pass


class Enveloppe(models.Model):
    dotation = models.CharField("Dotation", choices=DOTATION_CHOICES)
    montant = models.DecimalField(
        "Montant",
        max_digits=14,
        decimal_places=2,
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
    def delegation_root(self) -> "Enveloppe":
        if not self.is_deleguee:
            return self
        else:
            return self.deleguee_by.delegation_root

    @cached_property
    def enveloppe_projets_included(self):
        return Projet.objects.included_in_enveloppe(self)

    @property
    def montant_asked(self):
        return self.enveloppe_projets_included.aggregate(
            Sum("dossier_ds__demande_montant")
        )["dossier_ds__demande_montant__sum"]

    @cached_property
    def enveloppe_projets_processed(self):
        if self.is_deleguee:
            return ProgrammationProjet.objects.filter(
                enveloppe=self.delegation_root,
                dotation_projet__projet__in=self.enveloppe_projets_included,
            )
        return ProgrammationProjet.objects.filter(enveloppe=self)

    @property
    def accepted_montant(self):
        return (
            self.enveloppe_projets_processed.filter(
                status=ProgrammationProjet.STATUS_ACCEPTED
            ).aggregate(Sum("montant"))["montant__sum"]
            or 0
        )

    @property
    def validated_projets_count(self):
        return self.enveloppe_projets_processed.filter(
            status=ProgrammationProjet.STATUS_ACCEPTED
        ).count()

    @property
    def refused_projets_count(self):
        return self.enveloppe_projets_processed.filter(
            status=ProgrammationProjet.STATUS_REFUSED
        ).count()

    @property
    def demandeurs_count(self):
        return self.enveloppe_projets_included.distinct("demandeur").count()

    @property
    def projets_count(self):
        return self.enveloppe_projets_included.count()

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


class ProgrammationProjetQuerySet(models.QuerySet):
    def create(self, **kwargs):
        if "enveloppe" in kwargs:
            kwargs["enveloppe"] = kwargs["enveloppe"].delegation_root
        return super().create(**kwargs)

    def to_notify(self):
        return self.filter(dotation_projet__projet__in=Projet.objects.to_notify())

    def for_perimetre(self, perimetre):
        return self.filter(
            dotation_projet__projet__in=Projet.objects.for_perimetre(perimetre)
        )

    def visible_to_user(self, user):
        if user.is_staff:
            return self.all()
        return self.filter(dotation_projet__projet__in=Projet.objects.for_user(user))


class ProgrammationProjetManager(
    models.Manager.from_queryset(ProgrammationProjetQuerySet)
):
    pass


class ProgrammationProjet(models.Model):
    """
    Class used to store information about a Projet that is
    definitely accepted or refused on a given Enveloppe.
    """

    STATUS_ACCEPTED = "accepted"
    STATUS_REFUSED = "refused"
    STATUS_DISMISSED = "dismissed"
    STATUS_CHOICES = (
        (STATUS_ACCEPTED, "✅ Accepté"),
        (STATUS_REFUSED, "❌ Refusé"),
        (STATUS_DISMISSED, "⛔️ Classé sans suite"),
    )

    dotation_projet = models.OneToOneField(
        DotationProjet,
        on_delete=models.CASCADE,
        verbose_name="Dotation projet",
        related_name="programmation_projet",
    )
    enveloppe = models.ForeignKey(
        Enveloppe, on_delete=models.CASCADE, verbose_name="Enveloppe"
    )
    status = models.CharField(
        verbose_name="État", choices=STATUS_CHOICES, default=STATUS_ACCEPTED
    )
    montant = models.DecimalField(
        decimal_places=2, max_digits=14, verbose_name="Montant"
    )

    justification = models.TextField(
        verbose_name="Justification", blank=True, null=False, default=""
    )

    created_at = models.DateTimeField(
        verbose_name="Date de création", auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name="Date de dernière modification", auto_now=True
    )

    objects = ProgrammationProjetManager()

    class Meta:
        verbose_name = "Programmation projet"
        verbose_name_plural = "Programmations projet"

    def __str__(self):
        return f"Projet programmé {self.pk}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": self.projet.id},
        )

    @property
    def projet(self):
        return self.dotation_projet.projet

    @property
    def dossier(self):
        return self.projet.dossier_ds

    @property
    def taux(self):
        return compute_taux(self.montant, self.dotation_projet.assiette_or_cout_total)

    @property
    @deprecated("Use `Projet.to_notify` instead.")
    def to_notify(self):
        return self.projet.to_notify

    @property
    def dotation(self):
        return self.dotation_projet.dotation

    @property
    @deprecated("Use `Projet.notified_at` instead.")
    def notified_at(self):
        return self.projet.notified_at

    @notified_at.setter
    @deprecated("Use `Projet.notified_at` instead.")
    def notified_at(self, value):
        self.projet.notified_at = value

    @property
    def documents(self):
        from gsl_notification.models import (
            Arrete,
            ArreteEtLettreSignes,
            LettreNotification,
        )

        return sorted(
            (
                document
                for document in (
                    Arrete.objects.filter(programmation_projet=self).first(),
                    LettreNotification.objects.filter(
                        programmation_projet=self
                    ).first(),
                    ArreteEtLettreSignes.objects.filter(
                        programmation_projet=self
                    ).first(),
                    *list(self.annexes.prefetch_related("created_by").all()),
                )
                if document
            ),
            key=lambda d: d.created_at,
        )

    def clean(self):
        errors = {}
        self._validate_montant(errors)
        self._validate_enveloppe(errors)
        self._validate_for_refused_status(errors)
        if errors:
            raise ValidationError(errors)

    def _validate_montant(self, errors):
        if self.dotation_projet.assiette is not None:
            if self.montant and self.montant > self.dotation_projet.assiette:
                errors["montant"] = {
                    "Le montant de la programmation ne peut pas être supérieur à l'assiette du projet pour cette dotation."
                }
        else:
            if (
                self.montant
                and self.projet.dossier_ds.finance_cout_total
                and self.montant > self.projet.dossier_ds.finance_cout_total
            ):
                errors["montant"] = {
                    "Le montant de la programmation ne peut pas être supérieur au coût total du projet pour cette dotation."
                }

    def _validate_enveloppe(self, errors):
        if self.enveloppe.is_deleguee:
            errors["enveloppe"] = {
                "Une programmation ne peut pas être faite sur une enveloppe déléguée."
                "Il faut programmer sur l'enveloppe mère."
            }

        if not self.enveloppe.perimetre.contains_or_equal(self.projet.perimetre):
            errors["enveloppe"] = {
                "Le périmètre de l'enveloppe ne contient pas le périmètre du projet."
            }

        if self.enveloppe.dotation != self.dotation_projet.dotation:
            errors["enveloppe"] = {
                "La dotation de l'enveloppe ne correspond pas à celle du projet pour cette dotation."
            }

    def _validate_for_refused_status(self, errors):
        if self.status == self.STATUS_REFUSED:
            if self.montant != 0:
                errors["montant"] = {"Un projet refusé doit avoir un montant nul."}

    @cached_property
    def documents_summary(self):
        summary = list()
        if hasattr(self, "arrete_et_lettre_signes"):
            summary.append("1 arrêté et lettre signés")
        else:
            if hasattr(self, "arrete"):
                summary.append("1 arrêté généré")
            if hasattr(self, "lettre_notification"):
                summary.append("1 lettre générée")

        annexes_count = self.annexes.count()
        if annexes_count != 0:
            plural = "s" if annexes_count > 1 else ""
            summary.append(f"{annexes_count} annexe{plural}")

        return summary
