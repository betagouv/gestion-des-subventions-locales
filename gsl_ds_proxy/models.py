import hashlib
import secrets

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
    instructeurs = models.ManyToManyField(
        "gsl_demarches_simplifiees.Profile",
        verbose_name="Instructeurs autorisés",
        blank=True,
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

    def save(self, *args, **kwargs):
        if not self.key_hash:
            plaintext = secrets.token_hex(32)
            self.key_hash = self.hash_key(plaintext)
            self._plaintext_key = plaintext
        super().save(*args, **kwargs)
