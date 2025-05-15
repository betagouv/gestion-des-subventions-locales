from django.contrib import admin
from django.db.models import Count
from import_export.admin import ImportExportMixin

from gsl_core.admin import AllPermsForStaffUser
from gsl_core.templatetags.gsl_filters import euro, percent

from .models import Enveloppe, ProgrammationProjet
from .resources import EnveloppeDETRResource, EnveloppeDSILResource


@admin.register(Enveloppe)
class EnveloppeAdmin(AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin):
    resource_classes = (EnveloppeDETRResource, EnveloppeDSILResource)
    list_display = (
        "__str__",
        "formatted_amount",
        "dotation",
        "annee",
        "simulations_count",
    )
    list_filter = ("dotation", "annee")
    search_fields = (
        "dotation",
        "annee",
        "perimetre__region__name",
        "perimetre__departement__name",
        "perimetre__arrondissement__name",
    )
    autocomplete_fields = (
        "deleguee_by",
        "perimetre",
    )

    def formatted_amount(self, obj):
        return euro(obj.montant)

    formatted_amount.admin_order_field = "montant"
    formatted_amount.short_description = "Montant"

    def simulations_count(self, obj) -> int:
        return obj.simulations_count

    simulations_count.admin_order_field = "simulations_count"
    simulations_count.short_description = "Nb de simulations"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = (
            qs.select_related("perimetre")
            .select_related("perimetre__region")
            .select_related("perimetre__departement")
            .select_related("perimetre__arrondissement")
        )
        return qs.annotate(simulations_count=Count("simulation"))


@admin.register(ProgrammationProjet)
class ProgrammationProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "enveloppe",
        "status",
        "formatted_amount",
        "formatted_taux",
        "notified_at",
    )
    autocomplete_fields = ("enveloppe",)
    raw_id_fields = ("dotation_projet",)
    readonly_fields = ("created_at", "updated_at")

    def formatted_amount(self, obj):
        return euro(obj.montant)

    formatted_amount.admin_order_field = "montant"
    formatted_amount.short_description = "Montant"

    def formatted_taux(self, obj):
        return percent(obj.taux)

    formatted_taux.admin_order_field = "taux"
    formatted_taux.short_description = "Taux"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related(
            "enveloppe",
            "enveloppe__perimetre",
            "enveloppe__perimetre__region",
            "enveloppe__perimetre__departement",
            "enveloppe__perimetre__arrondissement",
        )
        return qs
