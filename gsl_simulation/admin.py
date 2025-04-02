from django.contrib import admin
from django.db.models import Count

from gsl_core.admin import AllPermsForStaffUser
from gsl_core.models import Perimetre

from .models import Simulation, SimulationProjet


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
    list_display = (
        "__str__",
        "enveloppe",
        "created_at",
        "slug",
        "simulationprojets_count",
    )
    list_filter = (
        "enveloppe__annee",
        "enveloppe__dotation",
        SimulationRegionFilter,
        SimulationDepartementFilter,
    )

    def simulationprojets_count(self, obj) -> int:
        return obj.simulationprojets_count

    simulationprojets_count.admin_order_field = "simulationprojets_count"
    simulationprojets_count.short_description = "Nb de projets"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = (
            qs.select_related("enveloppe")
            .select_related("enveloppe__perimetre")
            .select_related("enveloppe__perimetre__region")
            .select_related("enveloppe__perimetre__departement")
            .select_related("enveloppe__perimetre__arrondissement")
        )
        qs = qs.annotate(simulationprojets_count=Count("simulationprojet"))
        return qs


@admin.register(SimulationProjet)
class SimulationProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "projet__dossier_ds__projet_intitule",
        "simulation__slug",
        "status",
    )
    search_fields = ("projet__dossier_ds__projet_intitule",)
    raw_id_fields = ("projet", "simulation")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = (
            qs.select_related("projet")
            .select_related("projet__dossier_ds")
            .select_related("simulation")
        )
        return qs
