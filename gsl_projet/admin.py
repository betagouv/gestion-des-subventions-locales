from django.contrib import admin
from django.db.models import Count

from gsl_core.admin import AllPermsForStaffUser
from gsl_simulation.models import SimulationProjet

from .models import Demandeur, DotationProjet, Projet


@admin.register(Demandeur)
class DemandeurAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address",)
    list_display = ("name", "address__commune__departement")
    search_fields = ("name", "siret", "address__commune__name")


class DotationProjetInline(admin.TabularInline):
    model = DotationProjet
    extra = 0
    show_change_link = True


class SimulationProjetInline(admin.TabularInline):
    model = SimulationProjet
    extra = 0
    show_change_link = True
    fields = [
        "simulation",
        "montant",
        "taux",
        "status",
        "created_at",
        "updated_at",
    ]
    readonly_fields = [
        "simulation",
        "montant",
        "taux",
        "status",
        "created_at",
        "updated_at",
    ]


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "departement", "demandeur", "dossier_ds")
    list_display = ("__str__", "status", "address", "departement", "dotations")
    list_filter = ("status", "departement")
    actions = ("refresh_from_dossier",)
    inlines = [
        DotationProjetInline,
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("address").select_related("departement")
        qs = qs.prefetch_related("dotationprojet_set")
        return qs

    @admin.action(description="Rafraîchir depuis le dossier DS")
    def refresh_from_dossier(self, request, queryset):
        from gsl_projet.tasks import update_projet_from_dossier

        for projet in queryset.select_related("dossier_ds"):
            update_projet_from_dossier.delay(projet.dossier_ds.ds_number)

    def dotations(self, obj):
        return ", ".join(obj.dotations)


@admin.register(DotationProjet)
class DotationProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("projet",)
    list_display = ("id", "projet", "dotation", "status", "simulation_count")
    list_filter = ("dotation", "status")
    inlines = [SimulationProjetInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(simulation_count=Count("simulationprojet"))
        qs = qs.select_related("projet", "projet__dossier_ds")
        qs = qs.prefetch_related("simulationprojet_set")
        return qs

    def simulation_count(self, obj):
        return obj.simulation_count
