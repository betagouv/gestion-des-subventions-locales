from import_export import resources
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from .models import Arrondissement, Departement, Region


class RegionResource(resources.ModelResource):
    """
    Documentation for the imported CSV files is available at
    https://www.insee.fr/fr/information/7766585
    """

    insee_code = Field(attribute="insee_code", column_name="REG")
    name = Field(attribute="name", column_name="NCCENR")

    class Meta:
        model = Region
        import_id_fields = ("insee_code",)


class DepartementResource(resources.ModelResource):
    insee_code = Field(attribute="insee_code", column_name="DEP")
    name = Field(attribute="name", column_name="NCCENR")
    region = Field(
        attribute="region",
        column_name="REG",
        widget=ForeignKeyWidget(Region, field="insee_code"),
    )

    class Meta:
        model = Departement
        import_id_fields = ("insee_code",)


class ArrondissementResource(resources.ModelResource):
    insee_code = Field(attribute="insee_code", column_name="ARR")
    name = Field(attribute="name", column_name="NCCENR")
    departement = Field(
        attribute="departement",
        column_name="DEP",
        widget=ForeignKeyWidget(Departement, field="insee_code"),
    )

    class Meta:
        model = Arrondissement
        import_id_fields = ("insee_code",)
