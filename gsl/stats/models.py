from django.db import models

from gsl.projet.constants import DS_STATE_VALUES
from gsl.projet.utils.utils import compute_taux
from gsl_core.models import ImportState


class Subvention(models.Model):
    """Une ligne = une aide versée (ou en cours d'instruction, pour Fonds Vert) à une collectivité,
    quelle que soit la source d'import.
    """

    SOURCE_DGCL = "dgcl"
    SOURCE_FONDS_VERT = "fonds_vert"
    SOURCE_CHOICES = (
        (SOURCE_DGCL, "DGCL"),
        (SOURCE_FONDS_VERT, "Fonds Vert"),
    )

    # Utile pour les importeurs pour l'upsert
    importer_key = models.CharField(
        max_length=255, editable=False, verbose_name="Clé d'import"
    )
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
    # Identifiant DS du dossier (Fonds Vert uniquement), conservé à titre
    # informatif pour retrouver le dossier d'origine.
    dossier_number = models.IntegerField(
        null=True, blank=True, verbose_name="Numéro de dossier DS"
    )

    class Meta:
        verbose_name = "Subvention"
        verbose_name_plural = "Subventions"
        ordering = ["-exercice"]
        indexes = [
            models.Index(fields=["source", "importer_key"]),
        ]

    def __str__(self):
        return (
            f"{self.exercice} {self.dispositif} - {self.siren} - {self.intitule[:50]}"
        )

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

    Retient dans `data` :
    - "last_page" : la progression de l'appel en cours (utile pour
      diagnostiquer où il s'est arrêté en cas d'interruption réseau ou
      d'expiration du token) ; chaque appel repart néanmoins de la page 1,
      remise à 0 dès le début de l'appel et une fois la synchronisation
      terminée.
    - "date_derniere_modification" : la date de la dernière synchronisation
      complète réussie, envoyée à l'API (`date_derniere_modification__gte`)
      pour ne récupérer que les dossiers modifiés depuis lors. Absente au
      premier import (import complet), et effacée par `--restart` pour en
      forcer un nouveau.
    """

    KEY = "fonds_vert"

    class Meta:
        proxy = True
        verbose_name = "État de l'import Fonds Vert"
        verbose_name_plural = "État de l'import Fonds Vert"

    def __str__(self):
        date_derniere_modification = self.data.get("date_derniere_modification")
        if date_derniere_modification:
            return f"Fonds Vert — dossiers modifiés jusqu'au {date_derniere_modification} (exclu)"
        return "Fonds Vert — aucune synchronisation complète encore réalisée"

    @classmethod
    def load(cls) -> "FondsVertImportState":
        return super().load(cls.KEY)
