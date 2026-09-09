from django.contrib import admin

from .models import FondsVertImportState, Subvention


@admin.register(Subvention)
class SubventionAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "exercice",
        "dispositif",
        "siren",
        "departement",
        "intitule",
        "montant_attribue",
    )
    list_filter = ("source", "exercice", "dispositif", "departement")
    search_fields = ("siren", "intitule")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FondsVertImportState)
class FondsVertImportStateAdmin(admin.ModelAdmin):
    """Réservé aux super-utilisateurs (voir AGENTS.md § Admin Permissions) : permet
    de consulter, et au besoin de corriger (ex: remettre à zéro le curseur de
    reprise), l'état de l'import Fonds Vert — stocké en JSON libre dans `data`
    (modèle générique `gsl_core.ImportState`, cf. sa docstring)."""

    list_display = ("key", "data", "updated_at")
