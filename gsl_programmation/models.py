from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q

from gsl_core.models import Collegue, Perimetre
from gsl_projet.models import Projet


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


class Simulation(models.Model):
    title = models.CharField(verbose_name="Titre")
    created_by = models.ForeignKey(Collegue, on_delete=models.SET_NULL, null=True)
    enveloppe = models.ForeignKey(
        Enveloppe, on_delete=models.PROTECT, verbose_name="Dotation associée"
    )
    slug = models.SlugField(verbose_name="Clé d’URL", unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Simulation de programmation"
        verbose_name_plural = "Simulations de programmation"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("programmation:simulation_detail", kwargs={"slug": self.slug})

    def get_projet_status_summary(self):
        default_status_summary = {
            SimulationProjet.STATUS_DRAFT: 0,
            SimulationProjet.STATUS_VALID: 0,
            SimulationProjet.STATUS_CANCELLED: 0,
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
    STATUS_DRAFT = "draft"
    STATUS_VALID = "valid"
    STATUS_CANCELLED = "cancelled"
    STATUS_PROVISOIRE = "provisoire"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "🔄 En traitement"),
        (STATUS_VALID, "✅  Accepté"),
        (STATUS_PROVISOIRE, "✔️ Accepté provisoirement"),
        (STATUS_CANCELLED, "❌ Refusé"),
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
        verbose_name="État", choices=STATUS_CHOICES, default=STATUS_DRAFT
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Simulation de programmation projet"
        verbose_name_plural = "Simulations de programmation projet"
        constraints = (
            models.UniqueConstraint(
                fields=("projet", "simulation", "enveloppe"),
                name="unique_projet_enveloppe_projet",
                nulls_distinct=True,
            ),
            models.UniqueConstraint(
                fields=("projet", "enveloppe"),
                condition=Q(status="valid"),
                name="unique_valid_simulation_per_project",
            ),
        )

    def __str__(self):
        return f"Simulation projet {self.pk}"
