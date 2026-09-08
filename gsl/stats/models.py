from django.db import models

from gsl.projet.utils.utils import compute_taux


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

    # --- Champs spécifiques Fonds Vert (nuls/vides pour la DGCL) ---

    montant_demande = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant demandé",
    )
    statut = models.CharField(max_length=30, blank=True, verbose_name="Statut")
    date_depot = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de dépôt"
    )
    # Identifiant DS du dossier, utilisé pour l'upsert idempotent depuis l'API
    # Fonds Vert. La DGCL n'a pas d'identifiant stable : son idempotence
    # repose sur la contrainte "unique_dgcl_subvention" ci-dessous.
    dossier_number = models.IntegerField(
        null=True, blank=True, unique=True, verbose_name="Numéro de dossier DS"
    )

    class Meta:
        verbose_name = "Subvention"
        verbose_name_plural = "Subventions"
        ordering = ["-exercice"]
        constraints = [
            # Scopée à la DGCL uniquement : plusieurs dossiers Fonds Vert d'un
            # même SIREN/exercice partagent souvent un intitulé vide, ce qui
            # entrerait sinon en collision entre dossiers distincts (chacun
            # déjà identifié de façon fiable par dossier_number).
            models.UniqueConstraint(
                fields=["exercice", "dispositif", "siren", "intitule"],
                condition=models.Q(source="dgcl"),
                name="unique_dgcl_subvention",
            ),
        ]

    def __str__(self):
        return (
            f"{self.exercice} {self.dispositif} - {self.siren} - {self.intitule[:50]}"
        )

    @property
    def taux_accorde(self):
        # Pas encore de montant attribué (dossier Fonds Vert non décidé) :
        # pas de taux à afficher.
        if self.montant_attribue is None:
            return None
        return compute_taux(self.montant_attribue, self.cout_total)


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
