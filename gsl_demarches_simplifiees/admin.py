from django.contrib import admin

from gsl_demarches_simplifiees.models import Demarche, Dossier, FieldMappingForHuman


@admin.register(Demarche)
class DemarcheAdmin(admin.ModelAdmin):
    readonly_fields = [field.name for field in Demarche._meta.get_fields()]


@admin.register(Dossier)
class DossierAdmin(admin.ModelAdmin):
    pass


@admin.register(FieldMappingForHuman)
class FieldMappingForHumanAdmin(admin.ModelAdmin):
    pass
