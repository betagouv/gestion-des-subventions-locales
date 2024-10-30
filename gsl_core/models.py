from django.contrib.auth.models import AbstractUser
from django.db import models


class Collegue(AbstractUser):
    proconnect_sub = models.UUIDField("Identifiant unique proconnect", null=True)
    proconnect_uid = models.CharField("ID chez le FI", default="")
    proconnect_idp_id = models.UUIDField("Identifiant du FI", null=True)
    proconnect_siret = models.CharField("SIRET", default="")
    proconnect_chorusdt = models.CharField(
        "Entité ministérielle / Matricule Agent", default=""
    )
