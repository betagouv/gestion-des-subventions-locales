from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from .models import Demarche, FieldMappingForComputer


class FieldMappingForComputerResource(resources.ModelResource):
    demarche = fields.Field(
        column_name="demarche",
        attribute="demarche",
        widget=ForeignKeyWidget(Demarche, field="ds_number"),
    )

    class Meta:
        model = FieldMappingForComputer
        import_id_fields = ("demarche", "ds_field_id")
