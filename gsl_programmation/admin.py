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
        "pk",
        "dotation",
        "annee",
        "region_name",
        "departement_name",
        "arrondissement_name",
        "formatted_amount",
        "simulations_count",
        "deleguee_by",
    )
    list_filter = (
        "dotation",
        "annee",
        "perimetre__region__name",
        "perimetre__departement__name",
    )
    search_fields = (
        "dotation",
        "annee",
        "region_name",
        "departement_name",
        "arrondissement_name",
    )
    autocomplete_fields = (
        "deleguee_by",
        "perimetre",
    )

    def region_name(self, obj):
        return obj.perimetre.region.name

    region_name.admin_order_field = "region_name"
    region_name.short_description = "Région"

    def departement_name(self, obj):
        return obj.perimetre.departement.name if obj.perimetre.departement else None

    departement_name.admin_order_field = "departement_name"
    departement_name.short_description = "Département"

    def arrondissement_name(self, obj):
        return (
            obj.perimetre.arrondissement.name if obj.perimetre.arrondissement else None
        )

    arrondissement_name.admin_order_field = "arrondissement_name"
    arrondissement_name.short_description = "Arrondissement"

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
        qs = qs.select_related(
            "perimetre",
            "perimetre__region",
            "perimetre__departement",
            "perimetre__arrondissement",
            "deleguee_by",
            "deleguee_by__perimetre",
            "deleguee_by__perimetre__region",
            "deleguee_by__perimetre__departement",
            "deleguee_by__perimetre__arrondissement",
        )
        return qs.annotate(simulations_count=Count("simulation"))


@admin.register(ProgrammationProjet)
class ProgrammationProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "pk",
        "enveloppe",
        "status",
        "formatted_amount",
        "formatted_taux",
        "notified_at",
    )
    autocomplete_fields = ("enveloppe",)
    raw_id_fields = ("dotation_projet",)
    readonly_fields = ("created_at", "updated_at")
    search_fields = ("dotation_projet__projet__dossier_ds__ds_number",)
    list_filter = (
        "status",
        "enveloppe__dotation",
        "enveloppe__annee",
        "enveloppe__perimetre__region__name",
        "enveloppe__perimetre__departement__name",
    )

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
            "dotation_projet",
            "dotation_projet__projet",
            "dotation_projet__projet__dossier_ds",
            "dotation_projet__projet__dossier_ds__ds_demarche",
        )
        return qs
