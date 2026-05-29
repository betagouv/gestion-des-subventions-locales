from django.contrib import admin

from gsl_historique.models import ProjetAction


@admin.register(ProjetAction)
class ProjetActionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "projet",
        "action_type",
        "dotation",
        "actor",
        "source",
    )
    list_filter = ("action_type", "source", "dotation")
    search_fields = ("projet__dossier_ds__ds_number",)
    readonly_fields = (
        "projet",
        "action_type",
        "created_at",
        "actor",
        "source",
        "dotation",
        "status",
        "montant",
        "document_name",
        "boolean_field",
        "boolean_value",
    )
    ordering = ("-created_at",)
