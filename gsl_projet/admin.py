from django.contrib import admin

from gsl_core.admin import AllPermsForStaffUser
from gsl_simulation.models import SimulationProjet

from .models import Demandeur, Projet


@admin.register(Demandeur)
class DemandeurAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address",)
    list_display = ("name", "address__commune__departement")
    search_fields = ("name", "siret", "address__commune__name")


class SimulationProjetInline(admin.TabularInline):
    model = SimulationProjet
    extra = 0
    show_change_link = True
    readonly_fields = [
        "simulation",
        "projet",
        "montant",
        "taux",
        "status",
    ]


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "departement", "demandeur", "dossier_ds")
    list_display = ("__str__", "status", "address", "departement")
    list_filter = ("status", "departement")
    actions = ("refresh_from_dossier",)
    inlines = [
        SimulationProjetInline,
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("address").select_related("departement")
        return qs

    @admin.action(description="Rafraîchir depuis le dossier DS")
    def refresh_from_dossier(self, request, queryset):
        from gsl_projet.tasks import update_projet_from_dossier

        for projet in queryset.select_related("dossier_ds"):
            update_projet_from_dossier.delay(projet.dossier_ds.ds_number)
