from typing import Optional

from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe

from gsl_core.admin import AllPermsForStaffUser
from gsl_core.models import Arrondissement
from gsl_programmation.models import ProgrammationProjet
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


class ProjetStatusFilter(admin.SimpleListFilter):
    title = "Statut"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return PROJET_STATUS_CHOICES

    def queryset(self, request, queryset: ProjetQuerySet):
        if self.value():
            return queryset.annotate_status().filter(_status=self.value())
        return queryset


class ArrondissementFilter(admin.SimpleListFilter):
    title = "Arrondissement"
    parameter_name = "arrondissement"

    def lookups(self, request, model_admin):
        departement_id = request.GET.get(
            "dossier_ds__perimetre__departement__insee_code__exact"
        )

        if not departement_id:
            return []  # Aucun arrondissement tant que département non choisi

        arrondissements = Arrondissement.objects.filter(
            departement__pk=departement_id
        ).order_by("insee_code")

        return [(a.insee_code, (f"{a.pk} - {a.name}")) for a in arrondissements]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                dossier_ds__perimetre__arrondissement__pk=self.value()
            )
        return queryset


@admin.register(Projet)
class ProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address", "demandeur", "dossier_ds")
    list_display = (
        "__str__",
        "dossier_ds__projet_intitule",
        "get_status_display",
        "dossier_departement",
        "dotations",
    )
    list_filter = (
        ProjetStatusFilter,
        ArrondissementFilter,
        "dossier_ds__perimetre__departement",
    )
    actions = ("refresh_from_dossier",)
    inlines = [
        DotationProjetInline,
    ]
    search_fields = ("dossier_ds__ds_number", "dossier_ds__projet_intitule")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("dossier_ds",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related(
            "dossier_ds",
            "dossier_ds__ds_data",
            "dossier_ds__ds_demarche",
            "dossier_ds__perimetre",
            "dossier_ds__perimetre__departement",
        )
        qs = qs.defer(
            "dossier_ds__ds_data__raw_data",
            "dossier_ds__ds_demarche__raw_ds_data",
        )
        qs = qs.prefetch_related("dotationprojet_set")
        return qs

    @admin.action(description="Rafraîchir depuis le dossier DN")
    def refresh_from_dossier(self, request, queryset):
        from gsl_projet.tasks import task_create_or_update_projet_and_co_from_dossier

        for projet in queryset.select_related("dossier_ds"):
            task_create_or_update_projet_and_co_from_dossier.delay(
                projet.dossier_ds.ds_number
            )

    def get_deleted_objects(self, objs, request):
        deleted_objects, model_count, perms_needed, protected = (
            super().get_deleted_objects(objs, request)
        )
        try:
            perms_needed.remove(DotationProjet._meta.verbose_name)
        except KeyError:
            pass
        return deleted_objects, model_count, perms_needed, protected

    def dotations(self, obj):
        return ", ".join(obj.dotations)

    def get_status_display(self, obj: Projet):
        return dict(PROJET_STATUS_CHOICES)[obj.status]

    get_status_display.short_description = "Statut"

    def dossier_departement(self, obj):
        return obj.dossier_ds.perimetre.departement.insee_code

    dossier_departement.short_description = "Département"
    dossier_departement.admin_order_field = (
        "dossier_ds__perimetre__departement__insee_code"
    )


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


class ProgrammationProjetInline(admin.TabularInline):
    model = ProgrammationProjet
    extra = 0
    show_change_link = True
    fields = [
        "enveloppe",
        "montant",
        "taux",
        "status",
        "created_at",
        "updated_at",
    ]
    readonly_fields = [
        "enveloppe",
        "montant",
        "taux",
        "status",
        "created_at",
        "updated_at",
    ]


@admin.register(DotationProjet)
class DotationProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("projet",)
    list_display = (
        "id",
        "dossier_link",
        "projet_link",
        "dotation",
        "status",
        "simulation_count",
    )
    search_fields = (
        "projet__dossier_ds__ds_number",
        "dotation",
        "projet__id",
    )
    list_filter = ("dotation", "status")
    inlines = [SimulationProjetInline, ProgrammationProjetInline]
    readonly_fields = ("created_at", "updated_at", "dossier_link", "projet_link")

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

    simulation_count.admin_order_field = "simulation_count"
    simulation_count.short_description = "Nb de simulations"

    def dossier_link(self, obj):
        if obj.projet.dossier_ds:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossier_change",
                args=[obj.projet.dossier_ds.id],
            )
            return mark_safe(f'<a href="{url}">{obj.projet.dossier_ds.ds_number}</a>')
        return None

    dossier_link.short_description = "Dossier"
    dossier_link.admin_order_field = "projet__dossier_ds__ds_number"

    def projet_link(self, obj):
        if obj.projet.dossier_ds:
            url = reverse(
                "admin:gsl_projet_projet_change",
                args=[obj.projet.id],
            )
            return mark_safe(f'<a href="{url}">{obj.projet.id}</a>')
        return None

    projet_link.short_description = "Projet"
    projet_link.admin_order_field = "projet__id"
