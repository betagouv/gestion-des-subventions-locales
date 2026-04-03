import secrets

from django.db import models

from gsl_core.models import BaseModel


class ProxyToken(BaseModel):
    key = models.CharField(
        "Clé API",
        max_length=64,
        unique=True,
        db_index=True,
        editable=False,
    )
    label = models.CharField("Libellé", max_length=255)
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

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_hex(32)
        super().save(*args, **kwargs)
