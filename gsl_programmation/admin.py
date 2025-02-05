from django.contrib import admin
from import_export.admin import ImportExportMixin

from gsl_core.admin import AllPermsForStaffUser

from .models import Enveloppe
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = (
            qs.select_related("perimetre")
            .select_related("perimetre__region")
            .select_related("perimetre__departement")
            .select_related("perimetre__arrondissement")
        )
        return qs
