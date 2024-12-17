from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self._meta.verbose_name} {self.pk}"


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
    postal_code = models.CharField("Code postal", blank=True)
    commune = models.ForeignKey(
        Commune, on_delete=models.PROTECT, null=True, blank=True
    )
    street_address = models.CharField("Adresse", blank=True)

    def __str__(self):
        return self.label

    def update_from_raw_ds_data(self, raw_ds_data):
        if isinstance(raw_ds_data, str):
            self.label = raw_ds_data
            return self
        self.label = str(raw_ds_data.get("label", ""))
        self.postal_code = str(raw_ds_data.get("postalCode", ""))
        self.street_address = str(raw_ds_data.get("streetAddress", ""))

        if all(
            raw_ds_data.get(key)
            for key in (
                "cityName",
                "cityCode",
                "departmentName",
                "departmentCode",
                "regionName",
                "regionCode",
            )
        ):
            region, _ = Region.objects.get_or_create(
                insee_code=raw_ds_data.get("regionCode"),
                name=raw_ds_data.get("regionName"),
            )
            departement, _ = Departement.objects.get_or_create(
                insee_code=raw_ds_data.get("departmentCode"),
                name=raw_ds_data.get("departmentName"),
                region=region,
            )
            commune, _ = Commune.objects.get_or_create(
                insee_code=raw_ds_data.get("cityCode"),
                name=raw_ds_data.get("cityName"),
                departement=departement,
            )
            self.commune = commune
        return self


class Perimetre(BaseModel):
    region = models.ForeignKey(
        Region,
        verbose_name="Région",
        on_delete=models.PROTECT,
    )
    departement = models.ForeignKey(
        Departement,
        verbose_name="Département",
        null=True,
        on_delete=models.PROTECT,
        blank=True,
    )
    arrondissement = models.ForeignKey(
        Arrondissement,
        verbose_name="Arrondissement",
        null=True,
        on_delete=models.PROTECT,
        blank=True,
    )

    class Meta:
        constraints = (
            UniqueConstraint(
                name="unicity_by_perimeter",
                fields=(
                    "region",
                    "departement",  # nullable
                    "arrondissement",  # nullable
                ),
                nulls_distinct=False,  # important because some fields are nullable
            ),
            # CheckConstraint(
            #     name="departement_belongs_to_region",
            #     violation_error_message="Le département sélectionné doit appartenir à sa région.",
            #     condition=Q(departement__region=F('region'))^Q(departement__isnull=True)
            # ),
            # CheckConstraint(
            #     name="arrondissement_belongs_to_departement",
            #     violation_error_message="L'arrondissement sélectionné doit appartenir à son département.",
            #     condition=Q(arrondissement__departement=F('departement'))^Q(arrondissement__isnull=True)
            # ),
        )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        if self.departement and self.region and self.departement.region != self.region:
            errors["departement"] = (
                "Le département doit appartenir à la même région que le périmètre."
            )

        if self.arrondissement and not self.departement:
            errors["arrondissement"] = (
                "Un arrondissement ne peut être sélectionné sans département."
            )
        elif (
            self.arrondissement
            and self.departement
            and self.arrondissement.departement != self.departement
        ):
            errors["arrondissement"] = (
                "L'arrondissement sélectionné doit appartenir à son département."
            )

        if errors:
            raise ValidationError(errors)

    # contraintes :
    # région obligatoire
    # si département : doit appartenir à la région
    # si arrondissement : département obligatoire et arrondissement doit appartenir au département

    # classe :
    # méthode de comparaison entre deux périmètres ?

    # utilisation de cette classe:
    # si utilisateur.perimetre inclut le projet.perimetre : utilisateur peut voir le projet
    # projet vs enveloppes
    # utilisateurs vs enveloppes

    # sur un projet : pas forcément ajouter un périmètre, mais "juste" bien renseigner l'arrondissement
    # projet__arrondissement__region == utilisateur.perimetre__region, etc.

    # projet.objects.filter(perimetre__region=utilisateur.perimetre__region)
    # si utilisateur.perimetre__departement is None : ok la condition suffit
    # sinon on continue :
    # projets.filter(perimetre__departement=user.perimetre__departement)
    # idem pour l'arrondissemnt

    # enveloppes : droits en lecture différents des droits en écriture


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
    perimeter = models.ForeignKey(
        Perimetre, on_delete=models.PROTECT, null=True, blank=True
    )
