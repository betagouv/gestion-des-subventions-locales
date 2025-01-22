import random

from import_export import resources
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from gsl_core.models import Departement, Perimetre

from .models import Enveloppe


class EnveloppeDETRResource(resources.ModelResource):
    # type = models.CharField("Type", choices=TYPE_CHOICES) # hardcodé
    montant = Field(attribute="montant")
    annee = Field(attribute="annee")
    perimetre = Field(
        attribute="perimetre",
        widget=ForeignKeyWidget(Perimetre),
    )
    enveloppe_id = Field(attribute="id")

    def before_import(self, dataset, **kwargs):
        # mimic a 'dynamic field'
        dataset.headers.append("enveloppe_id")
        dataset.headers.append("type")
        super().before_import(dataset, **kwargs)

    def before_import_row(self, row, **kwargs):
        row["enveloppe_id"] = None
        row["type"] = Enveloppe.TYPE_DETR
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
            perimetre=perimetre, type=row["type"], annee=row["annee"]
        )
        if enveloppe_qs.exists():
            row["enveloppe_id"] = enveloppe_qs.get().id

    class Meta:
        model = Enveloppe
        import_id_fields = ("enveloppe_id",)
        fields = ("enveloppe_id", "montant", "annee", "perimetre", "type")


class EnveloppeDSILResource(EnveloppeDETRResource):
    def before_import_row(self, row, **kwargs):
        # author_name = row["author"]
        # Author.objects.get_or_create(name=author_name, defaults={"name": author_name})
        row["type"] = Enveloppe.TYPE_DSIL
        row["enveloppe_id"] = random.choice((1, 2, 2, 3, 4))
