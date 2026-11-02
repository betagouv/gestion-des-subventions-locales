import hashlib
import secrets

from django.core.exceptions import ValidationError
from django.db import models

from gsl.core.models import BaseModel


class ProxyToken(BaseModel):
    key_hash = models.CharField(
        "Empreinte de clé API",
        max_length=64,
        unique=True,
        db_index=True,
        editable=False,
    )
    label = models.CharField("Libellé", max_length=255)
    demarche = models.ForeignKey(
        "gsl_demarches_simplifiees.Demarche",
        verbose_name="Démarche autorisée",
        on_delete=models.PROTECT,
        related_name="proxy_tokens",
    )
    groupe_instructeur_ds_id = models.CharField(
        "ID du groupe instructeur DS",
        max_length=255,
        blank=True,
        db_index=True,
    )
    is_active = models.BooleanField("Actif", default=False)

    class Meta:
        verbose_name = "Token proxy DS"
        verbose_name_plural = "Tokens proxy DS"

    def __str__(self):
        return self.label

    @staticmethod
    def hash_key(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    def clean(self):
        super().clean()
        if not self.is_active or not self.groupe_instructeur_ds_id:
            return
        raw = (self.demarche.raw_ds_data or {}) if self.demarche_id else {}
        groupes = raw.get("groupeInstructeurs") or []
        known_ids = {g.get("id") for g in groupes}
        if self.groupe_instructeur_ds_id not in known_ids:
            raise ValidationError(
                {
                    "groupe_instructeur_ds_id": (
                        "Le groupe instructeur sélectionné n'appartient pas "
                        "à la démarche."
                    )
                }
            )

    def save(self, *args, **kwargs):
        if not self.key_hash:
            plaintext = secrets.token_hex(32)
            self.key_hash = self.hash_key(plaintext)
            self._plaintext_key = plaintext
        super().save(*args, **kwargs)


class ProxyRequestLog(models.Model):
    """One row per GraphQL request forwarded to DN, read by Metabase."""

    class Outcome(models.TextChoices):
        OK = "ok", "Succès"
        SCOPE_ERROR = "scope_error", "Hors périmètre"
        VERBATIM_FORWARD = "verbatim_forward", "Erreur DN transmise"

    created_at = models.DateTimeField("Date", auto_now_add=True, db_index=True)
    request_id = models.CharField("ID de requête", max_length=32, unique=True)
    proxy_token = models.ForeignKey(
        ProxyToken,
        verbose_name="Token proxy",
        on_delete=models.SET_NULL,
        null=True,
        related_name="request_logs",
    )
    demarche_number = models.IntegerField("Numéro de démarche")
    operation_name = models.CharField("Opération", max_length=255, blank=True)
    root_field = models.CharField("Champ racine", max_length=64)
    outcome = models.CharField("Résultat", max_length=32, choices=Outcome.choices)
    elapsed_ms = models.PositiveIntegerField("Durée DN (ms)")
    dn_errors_count = models.PositiveIntegerField("Erreurs DN")
    dn_results_count = models.PositiveIntegerField(
        "Dossiers renvoyés par DN", null=True, blank=True
    )
    filtered_out_count = models.PositiveIntegerField(
        "Dossiers filtrés", null=True, blank=True
    )

    class Meta:
        verbose_name = "Requête proxy DN"
        verbose_name_plural = "Requêtes proxy DN"
        indexes = [models.Index(fields=["outcome", "created_at"])]

    def __str__(self):
        return self.request_id
