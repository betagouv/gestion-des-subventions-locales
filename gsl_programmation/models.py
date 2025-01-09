from django.db import models
from django.db.models import Case, F, Q, Sum, When

from gsl_core.models import Arrondissement, Collegue, Departement, Region
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
                    "annee",
                    "type",
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

    def get_total_cost(self):
        projets = Projet.objects.filter(simulationprojet__simulation=self).annotate(
            calculed_cost=Case(
                When(assiette__isnull=False, then=F("assiette")),
                default=F("dossier_ds__finance_cout_total"),
            )
        )

        return projets.aggregate(total=Sum("calculed_cost"))["total"]

    def get_total_amount_asked(self):
        return Projet.objects.filter(simulationprojet__simulation=self).aggregate(
            Sum("dossier_ds__demande_montant")
        )["dossier_ds__demande_montant__sum"]

    def get_total_amount_granted(self):
        return SimulationProjet.objects.filter(simulation=self).aggregate(
            Sum("montant")
        )["montant__sum"]


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
