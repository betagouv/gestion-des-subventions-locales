from django.db import models
from django.db.models import Count
from django.forms import ValidationError

from gsl_core.models import BaseModel, Collegue
from gsl_programmation.models import Enveloppe
from gsl_projet.models import DotationProjet
from gsl_projet.utils.utils import compute_taux


class Simulation(BaseModel):
    title = models.CharField(verbose_name="Titre")
    created_by = models.ForeignKey(Collegue, on_delete=models.SET_NULL, null=True)
    enveloppe = models.ForeignKey(
        Enveloppe, on_delete=models.PROTECT, verbose_name="Dotation associée"
    )
    slug = models.SlugField(verbose_name="Clé d’URL", unique=True, max_length=120)

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
            SimulationProjet.objects.filter(simulation=self)
            .values("status")
            .annotate(count=Count("status"))
        )

        summary = {item["status"]: item["count"] for item in status_count}

        return {**default_status_summary, **summary}


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
    dotation_projet = models.ForeignKey(
        DotationProjet, on_delete=models.CASCADE, null=True
    )
    simulation = models.ForeignKey(
        Simulation, on_delete=models.CASCADE, null=True, blank=True
    )

    montant = models.DecimalField(
        decimal_places=2, max_digits=14, verbose_name="Montant"
    )
    status = models.CharField(
        verbose_name="État", choices=STATUS_CHOICES, default=STATUS_PROCESSING
    )

    class Meta:
        verbose_name = "Projet de simulation"
        verbose_name_plural = "Projets de simulation"
        constraints = (
            models.UniqueConstraint(
                fields=("dotation_projet", "simulation"),
                name="unique_projet_simulation",
                nulls_distinct=True,
            ),
        )

    def __str__(self):
        return f"Simulation projet {self.pk}"

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("simulation:simulation-projet-detail", kwargs={"pk": self.pk})

    @property
    def projet(self):
        return self.dotation_projet.projet

    @property
    def enveloppe(self):
        return self.simulation.enveloppe

    @property
    def taux(self):
        return compute_taux(self.montant, self.dotation_projet.assiette_or_cout_total)

    def clean(self):
        errors = {}
        self._validate_montant(errors)
        self._validate_dotation(errors)
        if errors:
            raise ValidationError(errors)

    def _validate_montant(self, errors):
        if self.dotation_projet.assiette is not None:
            if self.montant and self.montant > self.dotation_projet.assiette:
                errors["montant"] = {
                    f"Le montant de la simulation ne peut pas être supérieur à l'assiette du projet ({self.projet.pk})."
                }
        else:
            if (
                self.montant
                and self.projet.dossier_ds.finance_cout_total
                and self.montant > self.projet.dossier_ds.finance_cout_total
            ):
                errors["montant"] = {
                    f"Le montant de la simulation ne peut pas être supérieur au coût total du projet ({self.projet.pk})."
                }

    def _validate_dotation(self, errors):
        if self.dotation_projet.dotation != self.simulation.enveloppe.dotation:
            errors["dotation_projet"] = {
                "La dotation du projet doit être la même que la dotation de la simulation."
            }
