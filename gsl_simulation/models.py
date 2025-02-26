from django.db import models
from django.db.models import Count

from gsl_core.models import Collegue
from gsl_programmation.models import Enveloppe
from gsl_projet.models import Projet


class Simulation(models.Model):
    title = models.CharField(verbose_name="Titre")
    created_by = models.ForeignKey(Collegue, on_delete=models.SET_NULL, null=True)
    enveloppe = models.ForeignKey(
        Enveloppe, on_delete=models.PROTECT, verbose_name="Dotation associée"
    )
    slug = models.SlugField(verbose_name="Clé d’URL", unique=True, max_length=120)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Simulation de programmation"
        verbose_name_plural = "Simulations de programmation"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("simulation:simulation-detail", kwargs={"slug": self.slug})

    def get_projet_status_summary(self):
        default_status_summary = {
            SimulationProjet.STATUS_PROCESSING: 0,
            SimulationProjet.STATUS_ACCEPTED: 0,
            SimulationProjet.STATUS_REFUSED: 0,
            SimulationProjet.STATUS_PROVISOIRE: 0,
            "notified": 0,  # TODO : add notified count
        }
        status_count = (
            SimulationProjet.objects.filter(simulation=self)
            .values("status")
            .annotate(count=Count("status"))
        )

        summary = {item["status"]: item["count"] for item in status_count}

        return {**default_status_summary, **summary}


class SimulationProjet(models.Model):
    STATUS_PROCESSING = "draft"
    STATUS_ACCEPTED = "valid"
    STATUS_REFUSED = "cancelled"
    STATUS_PROVISOIRE = "provisoire"
    STATUS_CHOICES = (
        (STATUS_PROCESSING, "🔄 En traitement"),
        (STATUS_ACCEPTED, "✅ Accepté"),
        (STATUS_PROVISOIRE, "✔️ Accepté provisoirement"),
        (STATUS_REFUSED, "❌ Refusé"),
    )
    projet = models.ForeignKey(Projet, on_delete=models.CASCADE)
    enveloppe = models.ForeignKey(Enveloppe, on_delete=models.CASCADE)
    simulation = models.ForeignKey(
        Simulation, on_delete=models.CASCADE, null=True, blank=True
    )

    montant = models.DecimalField(
        decimal_places=2, max_digits=14, verbose_name="Montant"
    )
    taux = models.DecimalField(decimal_places=2, max_digits=5, verbose_name="Taux")
    status = models.CharField(
        verbose_name="État", choices=STATUS_CHOICES, default=STATUS_PROCESSING
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Simulation de programmation projet"
        verbose_name_plural = "Simulations de programmation projet"
        constraints = (
            models.UniqueConstraint(
                fields=("projet", "simulation", "enveloppe"),
                name="unique_projet_enveloppe_simulation",
                nulls_distinct=True,
            ),
        )

    def __str__(self):
        return f"Simulation projet {self.pk}"
