from django.contrib import admin

from gsl_demarches_simplifiees.models import (
    Demarche,
    Dossier,
    FieldMappingForComputer,
    FieldMappingForHuman,
)


@admin.register(Demarche)
class DemarcheAdmin(admin.ModelAdmin):
    readonly_fields = [field.name for field in Demarche._meta.get_fields()]
    list_display = ("ds_number", "ds_title", "ds_state")


@admin.register(Dossier)
class DossierAdmin(admin.ModelAdmin):
    pass


@admin.register(FieldMappingForHuman)
class FieldMappingForHumanAdmin(admin.ModelAdmin):
    pass


@admin.register(FieldMappingForComputer)
class FieldMappingForComputerAdmin(admin.ModelAdmin):
    readonly_fields = [
        field.name for field in FieldMappingForComputer._meta.get_fields()
    ]
    list_display = ("ds_field_id", "ds_field_label", "django_field", "demarche")
