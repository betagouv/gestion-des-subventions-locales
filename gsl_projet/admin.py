from django.contrib import admin

from gsl_core.admin import AllPermsForStaffUser

from .models import Demandeur, Projet


@admin.register(Demandeur)
class DemandeurAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "arrondissement", "departement")
    list_display = ("name", "departement", "arrondissement")


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "demandeur", "dossier_ds")
    list_display = (
        "__str__",
        "dossier_ds__ds_state",
        "demandeur__departement",
        "demandeur__arrondissement",
    )
    list_filter = ("demandeur__departement", "dossier_ds__ds_state")
    actions = ("refresh_from_dossier",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = (
            qs.select_related("address")
            .select_related("demandeur")
            .select_related("demandeur__departement")
            .select_related("demandeur__arrondissement")
        )
        return qs

    @admin.action(description="Rafraîchir depuis le dossier DS")
    def refresh_from_dossier(self, request, queryset):
        from gsl_projet.tasks import update_projet_from_dossier

        for projet in queryset.select_related("dossier_ds"):
            update_projet_from_dossier.delay(projet.dossier_ds.ds_number)
