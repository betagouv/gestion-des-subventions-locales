from django.contrib import admin

from gsl_core.admin import AllPermsForStaffUser

from .models import Demandeur, Projet


@admin.register(Demandeur)
class DemandeurAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "arrondissement", "departement")
    list_display = ("name", "departement", "arrondissement")


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "departement", "demandeur", "dossier_ds")
    list_display = ("__str__", "dossier_ds__ds_state", "address", "departement")
    list_filter = ("departement", "dossier_ds__ds_state")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("address").select_related("departement")
        return qs
