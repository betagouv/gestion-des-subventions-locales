from django.db import models

from gsl.projet.constants import DS_STATE_VALUES
from gsl.projet.utils.utils import compute_taux
from gsl_core.models import ImportState


class Subvention(models.Model):
    """Fusion de SubventionDgcl et SubventionFondsVert : une ligne = une aide
    versée (ou en cours d'instruction, pour Fonds Vert) à une collectivité,
    quelle que soit la source d'import.
    """

    SOURCE_DGCL = "dgcl"
    SOURCE_FONDS_VERT = "fonds_vert"
    SOURCE_CHOICES = (
        (SOURCE_DGCL, "DGCL"),
        (SOURCE_FONDS_VERT, "Fonds Vert"),
    )

    unique_key = models.CharField(
        max_length=255, unique=True, editable=False, verbose_name="Clé unique"
    )

    # --- Champs communs (DGCL et Fonds Vert) ---
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, verbose_name="Source"
    )
    siren = models.CharField(max_length=9, db_index=True, verbose_name="SIREN")
    exercice = models.PositiveSmallIntegerField(verbose_name="Exercice")
    dispositif = models.CharField(
        max_length=80, verbose_name="Dispositif"
    )  # DETR, DSIL, DPV, FONDS VERT (la DSID est ignorée à l'import)
    programme = models.PositiveSmallIntegerField(verbose_name="Programme")
    intitule = models.TextField(verbose_name="Intitulé du projet")
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
    cout_total = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Coût total"
    )
    montant_attribue = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant attribué",
    )

    montant_demande = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant demandé",
    )
    status = models.CharField(
        max_length=30, blank=True, choices=DS_STATE_VALUES, verbose_name="Statut"
    )
    date_depot = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de dépôt"
    )
    # Identifiant DS du dossier (Fonds Vert uniquement), conservé à titre
    # informatif pour retrouver le dossier d'origine. Ce n'est plus lui qui
    # porte l'unicité : c'est `unique_key`, cf. plus bas.
    dossier_number = models.IntegerField(
        null=True, blank=True, verbose_name="Numéro de dossier DS"
    )

    class Meta:
        verbose_name = "Subvention"
        verbose_name_plural = "Subventions"
        ordering = ["-exercice"]

    def __str__(self):
        return (
            f"{self.exercice} {self.dispositif} - {self.siren} - {self.intitule[:50]}"
        )

    def save(self, *args, **kwargs):
        self.unique_key = self.compute_unique_key(
            self.source,
            dossier_number=self.dossier_number,
            exercice=self.exercice,
            dispositif=self.dispositif,
            siren=self.siren,
            intitule=self.intitule,
        )
        super().save(*args, **kwargs)

    @staticmethod
    def compute_unique_key(
        source,
        dossier_number=None,
        exercice=None,
        dispositif=None,
        siren=None,
        intitule=None,
    ):
        if source == Subvention.SOURCE_FONDS_VERT:
            return f"{source}:{dossier_number}"
        return f"{source}:{exercice}:{dispositif}:{siren}:{intitule}"

    @property
    def taux_accorde(self):
        if self.montant_attribue is None:
            return None
        return compute_taux(self.montant_attribue, self.cout_total)


class FondsVertImportState(ImportState):
    """Proxy vers `gsl_core.ImportState` (ligne `key="fonds_vert"`), qui garde
    l'état de la synchronisation Fonds Vert visible dans l'admin "Suivi
    financier" alors que le modèle générique vit dans gsl_core, réutilisable
    par d'autres imports.

    Retient dans `data` la dernière page importée avec succès (clé
    "last_page") pour reprendre l'import à cet endroit après une interruption
    (erreur réseau, expiration du token, tâche relancée) plutôt que de tout
    refaire depuis la page 1. Remise à 0 une fois une synchronisation complète
    terminée avec succès.
    """

    KEY = "fonds_vert"

    class Meta:
        proxy = True
        verbose_name = "État de l'import Fonds Vert"
        verbose_name_plural = "État de l'import Fonds Vert"

    def __str__(self):
        return f"Fonds Vert — reprise à la page {self.data.get('last_page', 0)}"

    @classmethod
    def load(cls) -> "FondsVertImportState":
        return super().load(cls.KEY)
