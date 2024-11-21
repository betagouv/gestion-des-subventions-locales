from django.contrib import admin

from gsl_core.admin import AllPermsForStaffUser

from .models import (
    Demarche,
    Dossier,
    FieldMappingForComputer,
    FieldMappingForHuman,
)
from .tasks import task_refresh_dossier_from_saved_data


@admin.register(Demarche)
class DemarcheAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    readonly_fields = [field.name for field in Demarche._meta.get_fields()]
    list_display = ("ds_number", "ds_title", "ds_state")


@admin.register(Dossier)
class DossierAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_filter = ("ds_demarche__ds_number", "ds_state")
    list_display = ("ds_number", "ds_demarche__ds_number", "ds_state")
    fieldsets = (
        (
            "Informations générales",
            {"fields": ("ds_demarche", "ds_id", "ds_number", "ds_state")},
        ),
        (
            "Champs DS",
            {
                "classes": ("collapse", "open"),
                "fields": tuple(field.name for field in Dossier.MAPPED_FIELDS),
            },
        ),
        (
            "Dates",
            {
                "classes": ("collapse", "open"),
                "fields": (
                    "ds_date_depot",
                    "ds_date_passage_en_construction",
                    "ds_date_passage_en_instruction",
                    "ds_date_derniere_modification",
                    "ds_date_derniere_modification_champs",
                ),
            },
        ),
        (
            "Données brutes",
            {"classes": ("collapse", "open"), "fields": ("raw_ds_data",)},
        ),
    )
    actions = ("refresh_from_db",)
    raw_id_fields = ("projet_adresse",)

    @admin.action(description="Rafraîchir depuis la base de données")
    def refresh_from_db(self, request, queryset):
        for dossier in queryset:
            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)


@admin.register(FieldMappingForHuman)
class FieldMappingForHumanAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("label", "django_field")


@admin.register(FieldMappingForComputer)
class FieldMappingForComputerAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    readonly_fields = [
        field.name for field in FieldMappingForComputer._meta.get_fields()
    ]
    list_display = ("ds_field_id", "ds_field_label", "django_field", "demarche")
    list_filter = ("demarche__ds_number", "ds_field_type")
