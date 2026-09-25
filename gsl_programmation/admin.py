from django.contrib import admin
from django.db.models import Count
from import_export.admin import ImportExportMixin

from gsl.core.admin import AllPermsForStaffUser
from gsl.core.templatetags.gsl_filters import euro

from .models import Enveloppe
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
        "parent",
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
        "perimetre__region__name",
        "perimetre__departement__name",
        "perimetre__arrondissement__name",
    )
    autocomplete_fields = (
        "parent",
        "perimetre",
    )
    list_select_related = (
        "perimetre",
        "perimetre__region",
        "perimetre__departement",
        "perimetre__arrondissement",
        "parent",
        "parent__perimetre",
        "parent__perimetre__region",
        "parent__perimetre__departement",
        "parent__perimetre__arrondissement",
    )

    def region_name(self, obj):
        return obj.perimetre.region.name

    region_name.admin_order_field = "perimetre__region__name"
    region_name.short_description = "Région"

    def departement_name(self, obj):
        return obj.perimetre.departement.name if obj.perimetre.departement else None

    departement_name.admin_order_field = "perimetre__departement__name"
    departement_name.short_description = "Département"

    def arrondissement_name(self, obj):
        return (
            obj.perimetre.arrondissement.name if obj.perimetre.arrondissement else None
        )

    arrondissement_name.admin_order_field = "perimetre__arrondissement__name"
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
        return qs.annotate(simulations_count=Count("simulation"))
