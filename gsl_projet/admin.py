from django.contrib import admin
from unfold.admin import ModelAdmin

from gsl_core.admin import AllPermsForStaffUser

from .models import Demandeur, Projet


@admin.register(Demandeur)
class DemandeurAdmin(AllPermsForStaffUser, ModelAdmin):
    pass


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, ModelAdmin):
    raw_id_fields = ("address", "departement")
    list_display = ("__str__", "dossier_ds__ds_state", "address", "departement")
    list_filter = ("departement", "dossier_ds__ds_state")
