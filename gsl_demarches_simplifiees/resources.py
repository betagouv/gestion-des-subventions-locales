from import_export import resources

from .models import FieldMappingForComputer, FieldMappingForHuman


class FieldMappingForHumanResource(resources.ModelResource):
    class Meta:
        model = FieldMappingForHuman


class FieldMappingForComputerResource(resources.ModelResource):
    class Meta:
        model = FieldMappingForComputer
        import_id_fields = ("demarche", "ds_field_id")
