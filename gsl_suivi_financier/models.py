from django.db import models
from django.db.models import Case, Value, When

from gsl_projet.utils.utils import compute_taux


class Beneficiaire(models.Model):
    siren = models.CharField(max_length=9, primary_key=True, verbose_name="SIREN")
    nom = models.CharField(max_length=200, verbose_name="Nom")
    type = models.CharField(max_length=50, verbose_name="Type")

    class Meta:
        verbose_name = "Bénéficiaire"
        verbose_name_plural = "Bénéficiaires"
        ordering = [Case(When(nom="", then=Value(1)), default=Value(0)), "nom"]

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


class FondsVertImportState(models.Model):
    """État de la synchronisation Fonds Vert (ligne unique).

    Retient la dernière page importée avec succès pour reprendre l'import à cet
    endroit après une interruption (erreur réseau, expiration du token, tâche
    relancée) plutôt que de tout refaire depuis la page 1. Remise à 0 une fois
    une synchronisation complète terminée avec succès.
    """

    last_page = models.PositiveIntegerField(
        default=0, verbose_name="Dernière page importée"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        verbose_name = "État de l'import Fonds Vert"
        verbose_name_plural = "État de l'import Fonds Vert"

    def __str__(self):
        return f"Fonds Vert — reprise à la page {self.last_page}"

    @classmethod
    def load(cls) -> "FondsVertImportState":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SubventionFondsVert(models.Model):
    dossier_number = models.IntegerField(
        unique=True, verbose_name="Numéro de dossier DS"
    )
    beneficiaire = models.ForeignKey(
        Beneficiaire, on_delete=models.CASCADE, verbose_name="Bénéficiaire"
    )
    annee_millesime = models.PositiveSmallIntegerField(verbose_name="Millésime")
    demarche_number = models.IntegerField(verbose_name="Numéro de démarche DS")
    demarche_title = models.CharField(max_length=200, verbose_name="Démarche")
    nom_du_projet = models.TextField(verbose_name="Intitulé du projet")
    statut = models.CharField(max_length=30, verbose_name="Statut")
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
    montant_aide_demandee = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Montant demandé"
    )
    montant_subvention_attribuee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant attribué",
    )
    total_des_depenses = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Coût total"
    )
    date_depot = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de dépôt"
    )
    date_notification = models.DateField(
        null=True, blank=True, verbose_name="Date de notification"
    )

    class Meta:
        verbose_name = "Subvention Fonds Vert"
        verbose_name_plural = "Subventions Fonds Vert"
        ordering = ["-annee_millesime"]

    def __str__(self):
        return f"{self.annee_millesime} Fonds Vert - {self.beneficiaire} - {self.nom_du_projet[:50]}"

    @property
    def taux(self):
        return compute_taux(self.montant_aide_demandee, self.total_des_depenses)
