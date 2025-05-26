from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, UniqueConstraint


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
        ordering = ["name"]

    def __str__(self):
        return f"Région {self.insee_code} - {self.name}"


class Departement(BaseModel):
    insee_code = models.CharField("Code INSEE", unique=True, primary_key=True)
    name = models.CharField("Nom")
    region = models.ForeignKey(Region, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Département"
        ordering = ["insee_code"]

    def __str__(self):
        return f"Dép. {self.insee_code} - {self.name}"


class Arrondissement(BaseModel):
    insee_code = models.CharField("Code INSEE", unique=True, primary_key=True)
    name = models.CharField("Nom")
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)

    def __str__(self):
        return f"Arr. {self.insee_code} - {self.name}"


class Commune(BaseModel):
    insee_code = models.CharField("Code INSEE", unique=True, primary_key=True)
    name = models.CharField("Nom")
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)
    arrondissement = models.ForeignKey(
        Arrondissement, on_delete=models.PROTECT, null=True
    )

    def __str__(self):
        return f"Commune {self.insee_code} - {self.name}"


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
                defaults={
                    "name": raw_ds_data.get("departmentName"),
                    "region": region,
                },
            )
            commune, _ = Commune.objects.get_or_create(
                insee_code=raw_ds_data.get("cityCode"),
                defaults={
                    "name": raw_ds_data.get("cityName"),
                    "departement": departement,
                },
            )
            self.commune = commune
        return self


class PerimetreManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("arrondissement", "departement", "region")
            .order_by(
                F("region_id").asc(nulls_first=True),
                F("departement_id").asc(nulls_first=True),
                F("arrondissement_id").asc(nulls_first=True),
            )
        )


class Perimetre(BaseModel):
    TYPE_REGION = "Région"
    TYPE_DEPARTEMENT = "Département"
    TYPE_ARRONDISSEMENT = "Arrondissement"

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

    objects = PerimetreManager()

    class Meta:
        verbose_name = "Périmètre"
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
        )

    def __str__(self):
        name = f"{self.type} | {self.region.name}"
        if self.departement_id:
            name += f" - {self.departement.name}"
        if self.arrondissement_id:
            name += f" - {self.arrondissement.name}"
        return name

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

    def contains(self, other_perimetre):
        if self == other_perimetre:
            return False  # strict comparison
        if self.departement is None:  # self is a Region
            return (
                other_perimetre.departement is not None
                and other_perimetre.region == self.region
            )
        if self.arrondissement is None:  # self is a Departement
            return (
                other_perimetre.arrondissement is not None
                and other_perimetre.departement == self.departement
            )
        return False

    def contains_or_equal(self, other_perimetre):
        return self == other_perimetre or self.contains(other_perimetre)

    @property
    def type(self):
        if self.departement is None:
            return self.TYPE_REGION
        if self.arrondissement is None:
            return self.TYPE_DEPARTEMENT
        return self.TYPE_ARRONDISSEMENT

    @property
    def entity_name(self):
        if self.departement is None:
            return self.region.name
        if self.arrondissement is None:
            return self.departement.name
        return self.arrondissement.name

    def children(self):
        kwargs = {"region_id": self.region_id}
        if self.departement_id:
            kwargs["departement_id"] = self.departement_id
        if self.arrondissement_id:
            kwargs["arrondissement_id"] = self.arrondissement_id
        return Perimetre.objects.filter(**kwargs).exclude(id=self.id)

    def ancestors(self):
        if self.departement_id:
            region_perimetre_qs = Perimetre.objects.filter(
                region_id=self.region_id, departement_id=None, arrondissement_id=None
            )
            if self.arrondissement_id:
                departement_perimetre_qs = Perimetre.objects.filter(
                    region_id=self.region_id,
                    departement_id=self.departement_id,
                    arrondissement_id=None,
                )
                return region_perimetre_qs.union(departement_perimetre_qs)
            return region_perimetre_qs
        return Perimetre.objects.none()


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
    perimetre = models.ForeignKey(
        Perimetre, on_delete=models.PROTECT, null=True, blank=True
    )

    def __str__(self) -> str:
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.username
