from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe

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
        "id",
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
        "id",
        "dossier_link",
        "projet_link",
        "intitule",
        "simulation",
        "status",
    )
    search_fields = (
        "dotation_projet__projet__dossier_ds__projet_intitule",
        "dotation_projet__projet__id",
        "dotation_projet__projet__dossier_ds__ds_number",
    )
    raw_id_fields = (
        "dotation_projet",
        "simulation",
    )
    fields = (
        "dossier_link",
        "projet_link",
        "dotation_projet",
        "intitule",
        "simulation",
        "montant",
        "taux",
        "status",
        "created_at",
        "updated_at",
    )
    readonly_fields = (
        "intitule",
        "taux",
        "dossier_link",
        "projet_link",
        "created_at",
        "updated_at",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = (
            qs.select_related("dotation_projet__projet")
            .select_related("dotation_projet__projet__dossier_ds")
            .defer("dotation_projet__projet__dossier_ds__raw_ds_data")
            .select_related("simulation")
        )
        return qs

    def intitule(self, obj):
        return obj.dotation_projet.projet.dossier_ds.projet_intitule

    def dossier_link(self, obj):
        if obj.dotation_projet.projet.dossier_ds:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossier_change",
                args=[obj.dotation_projet.projet.dossier_ds.id],
            )
            return mark_safe(
                f'<a href="{url}">{obj.dotation_projet.projet.dossier_ds.ds_number}</a>'
            )
        return None

    dossier_link.short_description = "Dossier"
    dossier_link.admin_order_field = "dotation_projet__projet__dossier_ds__ds_number"

    def projet_link(self, obj):
        if obj.dotation_projet.projet.dossier_ds:
            url = reverse(
                "admin:gsl_projet_projet_change",
                args=[obj.dotation_projet.projet.id],
            )
            return mark_safe(f'<a href="{url}">{obj.dotation_projet.projet.id}</a>')
        return None

    projet_link.short_description = "Projet"
    projet_link.admin_order_field = "dotation_projet__projet__id"
