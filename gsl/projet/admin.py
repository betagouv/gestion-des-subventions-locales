from typing import Optional

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, F
from django.urls import reverse
from django.utils.safestring import mark_safe

from gsl.simulation.models import SimulationProjet
from gsl_core.admin import AllPermsForStaffUser
from gsl_core.models import Arrondissement
from gsl_core.templatetags.gsl_filters import percent
from gsl_programmation.models import Enveloppe

from .constants import PROJET_STATUS_ACCEPTED, PROJET_STATUS_CHOICES
from .models import EnveloppeProjet, Projet, ProjetQuerySet


class EnveloppeProjetInline(admin.TabularInline):
    model = EnveloppeProjet
    extra = 0
    show_change_link = True


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
    raw_id_fields = ("address", "dossier_ds")
    list_display = (
        "__str__",
        "is_active",
        "dossier_ds__projet_intitule",
        "get_status_display",
        "dossier_departement",
        "dotations",
        "notified_at",
    )
    list_filter = (
        "dossier_ds__is_active",
        ProjetStatusFilter,
        ArrondissementFilter,
        "dossier_ds__perimetre__departement",
    )
    actions = ("refresh_from_dossier",)
    inlines = [
        EnveloppeProjetInline,
    ]
    search_fields = ("dossier_ds__ds_number", "dossier_ds__projet_intitule")
    readonly_fields = ("created_at", "updated_at", "perimetre", "reporte")
    list_select_related = (
        "dossier_ds",
        "dossier_ds__ds_data",
        "dossier_ds__ds_demarche",
        "dossier_ds__perimetre",
        "dossier_ds__perimetre__departement",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.defer(
            "dossier_ds__ds_data__raw_data",
            "dossier_ds__ds_demarche__raw_ds_data",
        )
        return qs.prefetch_related("enveloppeprojet_set")

    @admin.action(description="Rafraîchir depuis le dossier DN")
    def refresh_from_dossier(self, request, queryset):
        from gsl.celery import priority_for_dispatch_count

        from .tasks import task_create_or_update_projet_and_co_from_dossier

        count = queryset.count()
        for projet in queryset.select_related("dossier_ds"):
            task_create_or_update_projet_and_co_from_dossier.apply_async(
                (projet.dossier_ds.ds_number,),
                priority=priority_for_dispatch_count(count),
            )

    def get_deleted_objects(self, objs, request):
        deleted_objects, model_count, perms_needed, protected = (
            super().get_deleted_objects(objs, request)
        )
        try:
            perms_needed.remove(EnveloppeProjet._meta.verbose_name)
        except KeyError:
            pass
        return deleted_objects, model_count, perms_needed, protected

    @admin.display(boolean=True, description="Actif")
    def is_active(self, obj: Projet):
        return obj.dossier_ds.is_active

    def dotations(self, obj):
        return ", ".join(obj.dotations)

    def get_status_display(self, obj: Projet):
        return dict(PROJET_STATUS_CHOICES)[obj.status] if obj.status else None

    get_status_display.short_description = "Statut"

    def dossier_departement(self, obj):
        return obj.dossier_ds.perimetre.departement.insee_code

    dossier_departement.short_description = "Département"
    dossier_departement.admin_order_field = (
        "dossier_ds__perimetre__departement__insee_code"
    )

    def reporte(self, obj: Projet):
        return obj.dossier_ds.demande_renouvellement or None

    reporte.short_description = "Report / Renouvellement"
    reporte.admin_order_field = "dossier_ds__demande_renouvellement"

    def perimetre(self, obj: Projet):
        return obj.perimetre

    perimetre.short_description = "Périmètre"


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


@admin.register(EnveloppeProjet)
class EnveloppeProjetAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("projet",)
    list_display = (
        "id",
        "is_active",
        "dossier_link",
        "projet_link",
        "dotation",
        "status",
        "enveloppe",
        "montant",
        "formatted_taux",
        "simulation_count",
    )
    search_fields = (
        "projet__dossier_ds__ds_number",
        "dotation",
        "projet__id",
    )
    list_filter = (
        "projet__dossier_ds__is_active",
        "dotation",
        "status",
        "enveloppe__annee",
        "enveloppe__perimetre__region__name",
        "enveloppe__perimetre__departement__name",
    )
    autocomplete_fields = ("enveloppe",)
    inlines = [SimulationProjetInline]
    actions = ("associer_enveloppe_2025",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "date_programmation",
        "dossier_link",
        "projet_link",
    )
    list_select_related = ("projet", "projet__dossier_ds")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(simulation_count=Count("simulationprojet"))
        return qs.prefetch_related("simulationprojet_set")

    @admin.action(description="Associer ce projet à l'enveloppe 2025")
    @transaction.atomic
    def associer_enveloppe_2025(self, request, queryset):
        invalid = queryset.exclude(status=PROJET_STATUS_ACCEPTED, enveloppe__annee=2026)
        if invalid.exists():
            self.message_user(
                request,
                f"{invalid.count()} projet(s) ignoré(s) : cette action n'est autorisée que pour les projets acceptés sur une enveloppe 2026.",
                messages.WARNING,
            )

        valid_qs = queryset.filter(
            status=PROJET_STATUS_ACCEPTED, enveloppe__annee=2026
        ).select_related("enveloppe__perimetre")
        enveloppe_projet_ids = list(valid_qs.values_list("id", flat=True))
        success_count = 0
        for enveloppe_projet in valid_qs:
            try:
                enveloppe_2025 = Enveloppe.objects.get(
                    dotation=enveloppe_projet.enveloppe.dotation,
                    perimetre=enveloppe_projet.enveloppe.perimetre,
                    annee=2025,
                    parent=None,
                )
            except Enveloppe.DoesNotExist:
                self.message_user(
                    request,
                    f"Aucune enveloppe 2025 trouvée pour le projet {enveloppe_projet.id} "
                    f"(dotation={enveloppe_projet.enveloppe.dotation}, périmètre={enveloppe_projet.enveloppe.perimetre}).",
                    messages.ERROR,
                )
                continue

            enveloppe_projet.accept_without_ds_update(
                montant=enveloppe_projet.montant,
                enveloppe=enveloppe_2025,
                actor=request.user,
            )
            enveloppe_projet.save()
            success_count += 1

        if success_count:
            self.message_user(
                request,
                f"{success_count} projet(s) associé(s) avec succès à l'enveloppe 2025.",
                messages.SUCCESS,
            )

        deleted_count, _ = SimulationProjet.objects.filter(
            enveloppe_projet__in=enveloppe_projet_ids,
            enveloppe_projet__enveloppe__annee__lt=F("simulation__enveloppe__annee"),
        ).delete()
        if deleted_count:
            self.message_user(
                request,
                f"{deleted_count} simulation(s) projet supprimée(s) suite au réassociement.",
                messages.SUCCESS,
            )

    def formatted_taux(self, obj):
        return percent(obj.taux_retenu)

    formatted_taux.short_description = "Taux"

    def has_delete_permission(self, request, obj: Optional[EnveloppeProjet] = None):
        perm = super().has_delete_permission(request, obj)
        if not perm:
            return False

        if obj is None:
            return True

        return obj.projet.enveloppeprojet_set.count() > 1

    @admin.display(boolean=True, description="Actif")
    def is_active(self, obj: EnveloppeProjet):
        return obj.projet.dossier_ds.is_active

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
