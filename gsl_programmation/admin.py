from django.contrib import admin
from import_export.admin import ImportExportMixin

from gsl_core.admin import AllPermsForStaffUser
from gsl_core.models import Perimetre

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


class SimulationRegionFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = "Région"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "region"

    def lookups(self, request, model_admin):
        for perimetre in (
            Perimetre.objects.filter(region__isnull=False, departement__isnull=True)
            .select_related("region")
            .order_by("region_id")
        ):
            yield (
                perimetre.region_id,
                f"{perimetre.region_id} {perimetre.region.name}",
            )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(enveloppe__perimetre__region=self.value())
        return queryset


class SimulationDepartementFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = "Département"

    # Parameter for the filter that will be used in the URL query.
    parameter_name = "departement"

    def lookups(self, request, model_admin):
        for perimetre in (
            Perimetre.objects.filter(
                departement__isnull=False, arrondissement__isnull=True
            )
            .select_related("departement")
            .order_by("departement_id")
        ):
            yield (
                perimetre.departement_id,
                f"{perimetre.departement.insee_code} {perimetre.departement.name}",
            )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(enveloppe__perimetre__departement=self.value())
        return queryset


@admin.register(Simulation)
class SimulationAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("created_by",)
    autocomplete_fields = ("enveloppe", "created_by")
    list_display = ("__str__", "enveloppe", "created_at")
    list_filter = (
        "enveloppe__annee",
        "enveloppe__type",
        SimulationRegionFilter,
        SimulationDepartementFilter,
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("enveloppe")
        return qs


@admin.register(SimulationProjet)
class SimulationProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("__str__", "projet__dossier_ds__projet_intitule")
    search_fields = ("projet__dossier_ds__projet_intitule",)
    raw_id_fields = ("projet",)
