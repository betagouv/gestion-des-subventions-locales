from django.contrib import admin
from import_export.admin import ImportExportMixin

from gsl_core.admin import AllPermsForStaffUser

from .models import Enveloppe, Simulation, SimulationProjet
from .resources import EnveloppeDETRResource, EnveloppeDSILResource


@admin.register(Enveloppe)
class EnveloppeAdmin(AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin):
    resource_classes = (EnveloppeDETRResource, EnveloppeDSILResource)
    list_display = ("__str__", "montant", "type", "annee")
    list_filter = ("type", "annee")
    search_fields = (
        "type",
        "annee",
        "perimetre__region__name",
        "perimetre__departement__name",
        "perimetre__arrondissement__name",
    )


@admin.register(Simulation)
class SimulationAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("created_by",)
    autocomplete_fields = ("enveloppe", "created_by")


@admin.register(SimulationProjet)
class SimulationProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("__str__", "projet__dossier_ds__projet_intitule")
    search_fields = ("projet__dossier_ds__projet_intitule",)
    raw_id_fields = ("projet",)
