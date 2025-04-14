from django.core.exceptions import ValidationError
from django.db import models

from gsl_core.models import Perimetre
from gsl_programmation.utils import is_there_less_or_equal_than_0_009_of_difference
from gsl_projet.constants import DOTATION_CHOICES, DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import DotationProjet, Projet


class Enveloppe(models.Model):
    dotation = models.CharField("Dotation", choices=DOTATION_CHOICES)
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
                name="unicity_by_perimeter_and_dotation",
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


class ProgrammationProjet(models.Model):
    """
    Class used to store information about a Projet that is
    definitely accepted or refused on a given Enveloppe.
    """

    STATUS_ACCEPTED = "accepted"
    STATUS_REFUSED = "refused"
    STATUS_CHOICES = (
        (STATUS_ACCEPTED, "✅ Accepté"),
        (STATUS_REFUSED, "❌ Refusé"),
    )

    # TODO pr_dotation remove this, and remplace it by a property ?
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE, verbose_name="Projet")
    dotation_projet = models.OneToOneField(
        DotationProjet, on_delete=models.CASCADE, verbose_name="Dotation projet"
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
    taux = models.DecimalField(decimal_places=2, max_digits=5, verbose_name="Taux")

    justification = models.TextField(
        verbose_name="Justification", blank=True, null=False, default=""
    )

    notified_at = models.DateTimeField(
        verbose_name="Date de notification", null=True, blank=True
    )
    created_at = models.DateTimeField(
        verbose_name="Date de création", auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name="Date de dernière modification", auto_now=True
    )

    class Meta:
        verbose_name = "Programmation projet"
        verbose_name_plural = "Programmations projet"

    def __str__(self):
        return f"Projet programmé {self.pk}"

    def clean(self):
        errors = {}
        self._validate_taux(errors)
        self._validate_montant(errors)
        self._validate_enveloppe(errors)
        self._validate_for_refused_status(errors)
        if errors:
            raise ValidationError(errors)

    def _validate_taux(self, errors):
        if self.taux and self.taux > 100:
            errors["taux"] = {
                "Le taux de la programmation ne peut pas être supérieur à 100."
            }

    def _validate_montant(self, errors):
        if self.dotation_projet.assiette is not None:
            if self.dotation_projet.assiette > 0:
                if not is_there_less_or_equal_than_0_009_of_difference(
                    self.taux, self.montant * 100 / self.dotation_projet.assiette
                ):
                    errors["taux"] = {
                        "Le taux et le montant de la programmation ne sont pas cohérents. "
                        f"Taux attendu : {str(round(self.montant * 100 / self.dotation_projet.assiette, 2))}"
                    }
            if self.montant and self.montant > self.dotation_projet.assiette:
                errors["montant"] = {
                    "Le montant de la programmation ne peut pas être supérieur à l'assiette du dotation projet."
                }
        else:
            if (
                self.montant
                # TODO pr_dotation use projet property instead of dotation_projet
                and self.dotation_projet.projet.dossier_ds.finance_cout_total
                and self.montant
                > self.dotation_projet.projet.dossier_ds.finance_cout_total
            ):
                errors["montant"] = {
                    "Le montant de la programmation ne peut pas être supérieur au coût total du dotation projet."
                }

    def _validate_enveloppe(self, errors):
        if self.enveloppe.is_deleguee:
            errors["enveloppe"] = {
                "Une programmation ne peut pas être faite sur une enveloppe déléguée."
                "Il faut programmer sur l'enveloppe mère."
            }

        # TODO pr_dotation use projet property instead of dotation_projet
        if not self.enveloppe.perimetre.contains_or_equal(
            self.dotation_projet.projet.perimetre
        ):
            errors["enveloppe"] = {
                "Le périmètre de l'enveloppe ne contient pas le périmètre du projet."
            }

        if self.enveloppe.dotation != self.dotation_projet.dotation:
            errors["enveloppe"] = {
                "La dotation de l'enveloppe ne correspond pas à celle du dotation projet."
            }

    def _validate_for_refused_status(self, errors):
        if self.status == self.STATUS_REFUSED:
            if self.montant != 0:
                errors["montant"] = {"Un projet refusé doit avoir un montant nul."}
            if self.taux != 0:
                errors["taux"] = {"Un projet refusé doit avoir un taux nul."}
