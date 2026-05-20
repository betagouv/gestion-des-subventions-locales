import hashlib
import secrets

from django.core.exceptions import ValidationError
from django.db import models

from gsl_core.models import BaseModel


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
    is_active = models.BooleanField("Actif", default=True)

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
        if not self.is_active:
            return
        if not self.groupe_instructeur_ds_id:
            raise ValidationError(
                {
                    "groupe_instructeur_ds_id": (
                        "Un groupe instructeur doit être sélectionné "
                        "pour activer le token."
                    )
                }
            )
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
