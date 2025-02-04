from django.contrib import admin
from django.db.models import JSONField
from django_json_widget.widgets import JSONEditorWidget
from import_export.admin import ImportExportMixin

from gsl_core.admin import AllPermsForStaffUser

from .models import (
    Arrondissement,
    Demarche,
    Dossier,
    FieldMappingForComputer,
    FieldMappingForHuman,
    PersonneMorale,
    Profile,
)
from .resources import FieldMappingForComputerResource, FieldMappingForHumanResource
from .tasks import (
    task_refresh_dossier_from_saved_data,
    task_refresh_field_mappings_on_demarche,
)


@admin.register(Demarche)
class DemarcheAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    readonly_fields = tuple(
        field.name
        for field in Demarche._meta.get_fields()
        if field.name != "raw_ds_data"
    )
    list_display = ("ds_number", "ds_title", "ds_state")
    actions = ("refresh_field_mappings",)
    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget},
    }
    fieldsets = (
        (None, {"fields": ("ds_number", "ds_id", "ds_title", "ds_state")}),
        ("Dates", {"fields": ("ds_date_creation", "ds_date_fermeture")}),
        (
            "Instructeurs",
            {
                "fields": ("ds_instructeurs",),
            },
        ),
        (
            "Données brutes",
            {
                "fields": ("raw_ds_data",),
                "classes": ("collapse", "open"),
            },
        ),
    )

    @admin.action(description="Rafraîchir les correspondances de champs")
    def refresh_field_mappings(self, request, queryset):
        for demarche in queryset:
            task_refresh_field_mappings_on_demarche(demarche.ds_number)


@admin.register(PersonneMorale)
class PersonneMoraleAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address",)
    list_display = ("__str__", "siret")
    fieldsets = (
        (
            "Informations",
            {
                "fields": (
                    "siret",
                    "raison_sociale",
                    "address",
                    "siren",
                    "naf",
                    "forme_juridique",
                )
            },
        ),
    )
    search_fields = ("siret", "siren", "raison_sociale")


@admin.register(Dossier)
class DossierAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_filter = ("ds_demarche__ds_number", "ds_state")
    list_display = (
        "ds_number",
        "ds_demarche__ds_number",
        "ds_state",
        "projet_intitule",
    )

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "ds_demarche",
                    "ds_id",
                    "ds_number",
                    "ds_state",
                    "ds_demandeur",
                )
            },
        ),
        (
            "Champs DS",
            {
                "classes": ("collapse", "open"),
                "fields": tuple(field.name for field in Dossier._MAPPED_CHAMPS_FIELDS),
            },
        ),
        (
            "Annotations DS",
            {
                "classes": ("collapse", "open"),
                "fields": tuple(
                    field.name for field in Dossier._MAPPED_ANNOTATIONS_FIELDS
                ),
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
                    "ds_date_traitement",
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
    raw_id_fields = (
        "projet_adresse",
        "ds_demandeur",
    )
    search_fields = ("ds_number", "projet_intitule")
    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget},
    }

    @admin.action(description="Rafraîchir depuis la base de données")
    def refresh_from_db(self, request, queryset):
        for dossier in queryset:
            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("ds_demarche")
        return qs


@admin.register(FieldMappingForHuman)
class FieldMappingForHumanAdmin(
    AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin
):
    list_display = ("label", "django_field", "demarche")
    resource_classes = (FieldMappingForHumanResource,)
    list_filter = ("demarche",)
    readonly_fields = ("demarche",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("demarche")
        return qs


@admin.register(FieldMappingForComputer)
class FieldMappingForComputerAdmin(
    AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin
):
    readonly_fields = [
        field.name
        for field in FieldMappingForComputer._meta.get_fields()
        if field.name != "django_field"
    ]
    list_display = ("ds_field_id", "ds_field_label", "django_field", "demarche")
    list_filter = ("demarche__ds_number", "ds_field_type")
    resource_classes = (FieldMappingForComputerResource,)


@admin.register(Profile)
class ProfileAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    pass


@admin.register(Arrondissement)
class ArrondissementAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("__str__", "core_arrondissement")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("core_arrondissement")
        return qs
