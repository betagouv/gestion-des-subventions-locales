from django.db import models

from gsl_projet.utils.utils import compute_taux


class Beneficiaire(models.Model):
    siren = models.CharField(max_length=9, primary_key=True, verbose_name="SIREN")
    nom = models.CharField(max_length=200, verbose_name="Nom")
    type = models.CharField(max_length=50, verbose_name="Type")

    class Meta:
        verbose_name = "Bénéficiaire"
        verbose_name_plural = "Bénéficiaires"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.siren})"


class SubventionDgcl(models.Model):
    beneficiaire = models.ForeignKey(
        Beneficiaire, on_delete=models.CASCADE, verbose_name="Bénéficiaire"
    )
    exercice = models.PositiveSmallIntegerField(verbose_name="Exercice")
    dispositif = models.CharField(
        max_length=80, verbose_name="Dispositif"
    )  # DETR, DSIL, DPV, DSID
    programme = models.PositiveSmallIntegerField(verbose_name="Programme")
    departement = models.ForeignKey(
        "gsl_core.Departement",
        on_delete=models.PROTECT,
        null=True,
        verbose_name="Département",
    )
    commune = models.ForeignKey(
        "gsl_core.Commune",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Commune",
    )
    intitule = models.TextField(verbose_name="Intitulé du projet")
    cout_ht = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Coût HT"
    )
    subvention = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Subvention"
    )

    class Meta:
        verbose_name = "Subvention DGCL"
        verbose_name_plural = "Subventions DGCL"
        unique_together = [("exercice", "dispositif", "beneficiaire", "intitule")]
        ordering = ["-exercice"]

    def __str__(self):
        return f"{self.exercice} {self.dispositif} - {self.beneficiaire} - {self.intitule[:50]}"

    @property
    def taux(self):
        return compute_taux(self.subvention, self.cout_ht)
