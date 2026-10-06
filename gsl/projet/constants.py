from typing import Literal

from django.db import models
from django.utils.functional import classproperty

# TODO move this file in gsl/core

DOTATION_DETR = "DETR"
DOTATION_DSIL = "DSIL"
DOTATIONS = (DOTATION_DETR, DOTATION_DSIL)
DOTATION_CHOICES = ((DOTATION_DETR, DOTATION_DETR), (DOTATION_DSIL, DOTATION_DSIL))

# TYPE
POSSIBLE_DOTATIONS = Literal["DETR", "DSIL"]

PREMIER_MOIS_DE_LA_CAMPAGNE_SUIVANTE = 10


class ProjetStatus(models.TextChoices):
    ACCEPTED = "accepted", "✅ Accepté"
    REFUSED = "refused", "❌ Refusé"
    PROCESSING = "processing", "🔄 En traitement"
    DISMISSED = "dismissed", "⛔️ Classé sans suite"

    @classproperty
    def FINAL(cls):
        return (cls.ACCEPTED, cls.REFUSED, cls.DISMISSED)

    @classproperty
    def NEGATIVE(cls):
        return (cls.REFUSED, cls.DISMISSED)


NOTIFICATION_STATUS_TO_GENERATE = "to_generate"
NOTIFICATION_STATUS_TO_SIGN = "to_sign"
NOTIFICATION_STATUS_TO_NOTIFY = "to_notify"
NOTIFICATION_STATUS_NOTIFIED = "notified"
NOTIFICATION_STATUS_CHOICES = (
    (NOTIFICATION_STATUS_TO_GENERATE, "À générer"),
    (NOTIFICATION_STATUS_TO_SIGN, "À signer"),
    (NOTIFICATION_STATUS_TO_NOTIFY, "À notifier"),
    (NOTIFICATION_STATUS_NOTIFIED, "Notifié"),
)

ARRETE = "arrete"
LETTRE = "lettre"
LETTRE_REFUS = "refus"

LETTRE_ET_ARRETE_SIGNES = "lettre_et_arrete_signes"
ANNEXE = "annexe"

MIN_DEMANDE_MONTANT_FOR_AVIS_DETR = 100_000

ANNUAIRE_ENTREPRISE_URL = "https://annuaire-entreprises.data.gouv.fr/entreprise/"
