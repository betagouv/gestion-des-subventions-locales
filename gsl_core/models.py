from django.contrib.auth.models import AbstractUser
from django.db import models


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self._meta.verbose_name} {self.pk}"


class Collegue(AbstractUser):
    proconnect_sub = models.UUIDField(
        "Identifiant unique proconnect", null=True, blank=True
    )
    proconnect_uid = models.CharField("ID chez le FI", default="", blank=True)
    proconnect_idp_id = models.UUIDField("Identifiant du FI", null=True, blank=True)
    proconnect_siret = models.CharField(
        "SIRET",
        default="",
        blank=True,
    )
    proconnect_chorusdt = models.CharField(
        "Entité ministérielle / Matricule Agent",
        default="",
        blank=True,
    )


class Region(BaseModel):
    insee_code = models.CharField("Code INSEE", unique=True, primary_key=True)
    name = models.CharField("Nom")

    class Meta:
        verbose_name = "Région"

    def __str__(self):
        return f"Région {self.name}"


class Departement(BaseModel):
    insee_code = models.CharField("Code INSEE", unique=True, primary_key=True)
    name = models.CharField("Nom")
    region = models.ForeignKey(Region, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Département"

    def __str__(self):
        return f"Département {self.name}"


class Commune(BaseModel):
    insee_code = models.CharField("Code INSEE", unique=True, primary_key=True)
    name = models.CharField("Nom")
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Commune {self.insee_code} {self.name}"


class Arrondissement(BaseModel):
    insee_code = models.CharField("Code INSEE", unique=True, primary_key=True)
    name = models.CharField("Nom")
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Arrondissement {self.name}"


class Adresse(BaseModel):
    label = models.TextField("Adresse complète")
    postal_code = models.CharField("Code postal")
    commune = models.ForeignKey(Commune, on_delete=models.PROTECT)
    street_address = models.CharField("Adresse")
