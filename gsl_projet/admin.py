from typing import Optional

from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.html import mark_safe

from gsl_core.admin import AllPermsForStaffUser
from gsl_simulation.models import SimulationProjet

from .constants import PROJET_STATUS_CHOICES
from .models import CategorieDetr, Demandeur, DotationProjet, Projet, ProjetQuerySet


@admin.register(Demandeur)
class DemandeurAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address",)
    list_display = ("name", "address__commune__departement")
    search_fields = ("name", "siret", "address__commune__name")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related(
            "address", "address__commune", "address__commune__departement"
        )
        return qs


class DotationProjetInline(admin.TabularInline):
    model = DotationProjet
    extra = 0
    show_change_link = True


@admin.register(CategorieDetr)
class CategorieDetrAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("departement_id", "annee", "rang", "libelle")
    list_filter = ("departement", "annee")


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


class ProjetStatusFilter(admin.SimpleListFilter):
    title = "Statut"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return PROJET_STATUS_CHOICES

    def queryset(self, request, queryset: ProjetQuerySet):
        if self.value():
            return queryset.annotate_status().filter(_status=self.value())
        return queryset


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "demandeur", "dossier_ds")
    list_display = (
        "__str__",
        "dossier_ds__projet_intitule",
        "get_status_display",
        "perimetre__departement",
        "dotations",
        "demarche",
    )
    list_filter = (
        ProjetStatusFilter,
        "perimetre__departement",
        "dossier_ds__ds_demarche__ds_number",
    )
    actions = ("refresh_from_dossier",)
    inlines = [
        DotationProjetInline,
    ]
    search_fields = ("dossier_ds__ds_number", "dossier_ds__projet_intitule")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("dossier_ds", "dossier_ds__ds_demarche")
        qs = qs.prefetch_related("dotationprojet_set", "perimetre__departement")
        return qs

    @admin.display(description="Démarche")
    def demarche(self, obj):
        return mark_safe(
            f'<a href="{reverse("admin:gsl_demarches_simplifiees_demarche_change", args=[obj.dossier_ds.ds_demarche.id])}">{obj.dossier_ds.ds_demarche.ds_number}</a>'
        )

    demarche.admin_order_field = "dossier_ds__ds_demarche__ds_number"

    @admin.action(description="Rafraîchir depuis le dossier DS")
    def refresh_from_dossier(self, request, queryset):
        from gsl_projet.tasks import task_create_or_update_projet_and_co_from_dossier

        for projet in queryset.select_related("dossier_ds"):
            task_create_or_update_projet_and_co_from_dossier.delay(
                projet.dossier_ds.ds_number
            )

    def dotations(self, obj):
        return ", ".join(obj.dotations)

    def get_status_display(self, obj: Projet):
        return dict(PROJET_STATUS_CHOICES)[obj.status]

    get_status_display.short_description = "Statut"


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

    def has_delete_permission(self, request, obj: Optional[DotationProjet] = None):
        perm = super().has_delete_permission(request, obj)
        if not perm:
            return False

        if obj is None:
            return True

        return obj.projet.dotationprojet_set.count() > 1

    def simulation_count(self, obj):
        return obj.simulation_count
