from django.db import models

from gsl_core.models import BaseModel
from gsl_projet.constants import DOTATION_CHOICES

# Chorus "Ty.val." (type de pièce) — column TV.
TV_LABELS = {
    "50": "Demandes d'achat",
    "51": "Commandes d'achat",
    "52": "Engagements frais de déplacement",
    "54": "Factures",
    "57": "Paiements",
    "58": "Demandes d'acompte",
    "60": "Pièces préenregistrées",
    "6B": "Liste de vérification FI-CA",
    "61": "Acomptes",
    "64": "Réimputations de fonds",
    "65": "Engagement de fonds",
    "66": "Transferts",
    "80": "Blocage de fonds",
    "81": "Réservation de fonds",
    "82": "Pré-engagement de fonds",
    "83": "Prévision de recettes",
    "84": "Réservation de paiements",
    "95": "Écritures de coûts secondaires (CO)",
}

# Chorus "type montant" — budget movement on an EJ poste (column TypeMtant).
TYPE_MONTANT_LABELS = {
    "0100": "Original",
    "0150": "Modification",
    "0200": "Réduction",
    "0210": "Réduction compensation de chèque",
    "0220": "Modification par réévaluation",
    "0250": "Payé",
    "0260": "Payé compensation de chèque",
    "0300": "Report exercice précédent (engagements)",
    "0350": "Report des engagements",
    "0351": "Report des engagements : report de fonds engagés",
    "0352": "Report des engagements : réduction de fonds engagés",
    "0360": "Solde des exercices précédents",
    "0400": "Entrée de blocage",
    "0500": "Ajustement par pièce suivante",
    "0600": "Changement d'imputation émetteur",
    "0650": "Changement d'imputation récepteur",
    "0700": "Décompte sortie",
    "0750": "Décompte entrée",
}

TYPES_MONTANT_PAYE = ("0250", "0260")


# No id in the source, so let's compose one.
LIGNE_IDENTITY_FIELDS = (
    "ej",
    "dn",
    "dotation",
    "montant",
    "date_transaction",
    "date_engagement",
    "tv",
    "type_montant",
    "poste",
    "compte_general",
)


class SuiviFinancier(BaseModel):
    ej = models.CharField("EJ (n° pièce Chorus)", max_length=20, db_index=True)
    dn = models.IntegerField("Numéro DN", null=True, blank=True, db_index=True)
    dotation = models.CharField(
        "Dotation", max_length=4, blank=True, choices=DOTATION_CHOICES
    )
    montant = models.DecimalField("Montant", max_digits=15, decimal_places=2)
    date_transaction = models.DateField(
        "Date de la transaction", null=True, blank=True, db_index=True
    )
    date_engagement = models.DateField("Date d'engagement", null=True, blank=True)
    tv = models.CharField("Type de pièce", max_length=5, blank=True, choices=TV_LABELS)
    type_montant = models.CharField(
        "Type de montant", max_length=10, blank=True, choices=TYPE_MONTANT_LABELS
    )
    # Used for the composed id.
    poste = models.CharField("Poste", max_length=10, blank=True)
    compte_general = models.CharField("Compte général", max_length=20, blank=True)

    class Meta:
        verbose_name = "Suivi financier"
        verbose_name_plural = "Suivis financiers"
        constraints = [
            models.UniqueConstraint(
                fields=LIGNE_IDENTITY_FIELDS,
                nulls_distinct=False,
                name="uniq_suivi_financier_ligne",
            )
        ]

    def __str__(self):
        return f"EJ {self.ej} — DN {self.dn} — {self.montant} €"

    @property
    def is_paye(self):
        return self.type_montant in TYPES_MONTANT_PAYE
