from django.db import models
from django.utils.functional import classproperty


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


class NotificationStatus(models.TextChoices):
    TO_GENERATE = "to_generate", "À générer"
    TO_SIGN = "to_sign", "À signer"
    TO_NOTIFY = "to_notify", "À notifier"
    NOTIFIED = "notified", "Notifié"


ARRETE = "arrete"
LETTRE = "lettre"
LETTRE_REFUS = "refus"

LETTRE_ET_ARRETE_SIGNES = "lettre_et_arrete_signes"
ANNEXE = "annexe"

MIN_DEMANDE_MONTANT_FOR_AVIS_DETR = 100_000
