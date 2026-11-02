from import_export import resources
from import_export.fields import Field
from import_export.widgets import BooleanWidget, ForeignKeyWidget

from dn.sync.models import Dotation
from gsl.core.models import Departement, Perimetre, Region

from .models import Enveloppe


class EnveloppeDETRResource(resources.ModelResource):
    montant = Field(attribute="montant")
    annee = Field(attribute="annee")
    perimetre = Field(
        attribute="perimetre",
        widget=ForeignKeyWidget(Perimetre),
    )
    enveloppe_id = Field(attribute="id")
    validee_dgcl = Field(attribute="validee_dgcl", widget=BooleanWidget())

    def __init__(self, enveloppes_officielles=False, **kwargs):
        super().__init__(**kwargs)
        self.enveloppes_officielles = enveloppes_officielles

    def before_import(self, dataset, **kwargs):
        # mimic a 'dynamic field'
        dataset.headers.append("enveloppe_id")
        dataset.headers.append("dotation")
        dataset.headers.append("validee_dgcl")
        super().before_import(dataset, **kwargs)

    def before_import_row(self, row, **kwargs):
        row["validee_dgcl"] = self.enveloppes_officielles
        self._set_perimetre_and_enveloppe_id(row)

    def _set_perimetre_and_enveloppe_id(self, row):
        row["enveloppe_id"] = None
        row["dotation"] = Dotation.DETR
        provided_departement_number = row["perimetre"]
        departement = Departement.objects.get(insee_code=provided_departement_number)
        perimetre, _ = Perimetre.objects.get_or_create(
            departement=departement,
            arrondissement__isnull=True,
            defaults={
                "departement": departement,
                "region": departement.region,
            },
        )
        row["perimetre"] = perimetre.id

        enveloppe_qs = Enveloppe.objects.filter(
            perimetre=perimetre, dotation=row["dotation"], annee=row["annee"]
        )
        if enveloppe_qs.exists():
            row["enveloppe_id"] = enveloppe_qs.get().id

    class Meta:
        model = Enveloppe
        import_id_fields = ("enveloppe_id",)
        fields = (
            "enveloppe_id",
            "montant",
            "annee",
            "perimetre",
            "dotation",
            "validee_dgcl",
        )


class EnveloppeDSILResource(EnveloppeDETRResource):
    def _set_perimetre_and_enveloppe_id(self, row):
        row["enveloppe_id"] = None
        row["dotation"] = Dotation.DSIL
        provided_region_number = row["perimetre"]
        region = Region.objects.get(insee_code=provided_region_number)
        perimetre, _ = Perimetre.objects.get_or_create(
            region=region,
            departement__isnull=True,
        )
        row["perimetre"] = perimetre.id

        enveloppe_qs = Enveloppe.objects.filter(
            perimetre=perimetre, dotation=row["dotation"], annee=row["annee"]
        )
        if enveloppe_qs.exists():
            row["enveloppe_id"] = enveloppe_qs.get().id
