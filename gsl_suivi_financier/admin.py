from django.contrib import admin

from .models import Beneficiaire, SubventionDgcl, SubventionFondsVert


@admin.register(Beneficiaire)
class BeneficiaireAdmin(admin.ModelAdmin):
    list_display = ("siren", "nom", "type")
    search_fields = ("siren", "nom")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubventionDgcl)
class SubventionDgclAdmin(admin.ModelAdmin):
    list_display = (
        "exercice",
        "dispositif",
        "beneficiaire",
        "departement",
        "intitule",
        "subvention",
    )
    list_filter = ("exercice", "dispositif", "departement")
    search_fields = ("beneficiaire__nom", "beneficiaire__siren", "intitule")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubventionFondsVert)
class SubventionFondsVertAdmin(admin.ModelAdmin):
    list_display = (
        "annee_millesime",
        "beneficiaire",
        "departement",
        "demarche_title",
        "nom_du_projet",
        "statut",
        "montant_subvention_attribuee",
    )
    list_filter = ("annee_millesime", "statut", "departement")
    search_fields = ("beneficiaire__nom", "beneficiaire__siren", "nom_du_projet")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
