from django.contrib import admin

from gsl_core.admin import AllPermsForStaffUser

from .models import Demandeur, Projet


@admin.register(Demandeur)
class DemandeurAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    pass


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "departement")
    list_display = ("__str__", "address", "departement")
