from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe
from import_export.admin import ImportExportMixin

from gsl_core.admin import AllPermsForStaffUser

from .importer.demarche import refresh_categories_operation_detr
from .models import (
    Arrondissement,
    CategorieDetr,
    CategorieDsil,
    CritereEligibiliteDetr,
    CritereEligibiliteDsil,
    Demarche,
    Departement,
    Dossier,
    FieldMappingForComputer,
    FieldMappingForHuman,
    NaturePorteurProjet,
    PersonneMorale,
    Profile,
)
from .resources import FieldMappingForComputerResource, FieldMappingForHumanResource
from .tasks import (
    task_refresh_dossier_from_saved_data,
    task_refresh_field_mappings_from_demarche_data,
    task_save_demarche_dossiers_from_ds,
    task_save_demarche_from_ds,
    task_save_one_dossier_from_ds,
)


@admin.register(Demarche)
class DemarcheAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    readonly_fields = tuple(
        field.name
        for field in Demarche._meta.get_fields()
        if field.name not in ("raw_ds_data")
    )
    list_display = (
        "ds_number",
        "ds_title",
        "ds_state",
        "dossiers_count",
        "fields_count",
        "link_to_json",
    )
    actions = (
        "save_demarche_from_ds",
        "refresh_field_mappings",
        "extract_detr_categories",
        "refresh_dossiers_from_ds",
        "refresh_new_or_modified_dossiers_from_ds",
    )
    fieldsets = (
        (None, {"fields": ("ds_number", "ds_id", "ds_title", "ds_state")}),
        (
            "Dates",
            {
                "fields": (
                    "ds_date_creation",
                    "ds_date_fermeture",
                    "active_revision_date",
                    "active_revision_id",
                )
            },
        ),
        (
            "Instructeurs",
            {
                "fields": ("ds_instructeurs",),
            },
        ),
        (
            "Données brutes",
            {
                "fields": ("raw_ds_data",),
                "classes": ("collapse", "open"),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.defer("raw_ds_data")
        return qs.annotate(dossier_count=Count("dossierdata"))

    def dossiers_count(self, obj) -> int:
        return obj.dossier_count

    dossiers_count.admin_order_field = "dossier_count"
    dossiers_count.short_description = "# de dossiers"

    def fields_count(self, obj) -> int:
        return obj.fieldmappingforcomputer_set.count()

    fields_count.admin_order_field = "fields_count"
    fields_count.short_description = "# de champs"

    @admin.action(
        description="🔍🛢️ Rafraîchir les correspondances de champs depuis les données sauvegardées"
    )
    def refresh_field_mappings(self, request, queryset):
        for demarche in queryset:
            task_refresh_field_mappings_from_demarche_data(demarche.ds_number)

    @admin.action(description="📃☁️ Rafraîchir la démarche depuis DN")
    def save_demarche_from_ds(self, request, queryset):
        for demarche in queryset:
            task_save_demarche_from_ds(demarche.ds_number)

    @admin.action(description="🔍 Extraction des catégories DETR")
    def extract_detr_categories(self, request, queryset):
        for demarche in queryset:
            refresh_categories_operation_detr(demarche.ds_number)

    @admin.action(
        description="🗂️☁️ Rafraîchir tous les dossiers de la démarche depuis DN"
    )
    def refresh_dossiers_from_ds(self, request, queryset):
        for demarche in queryset:
            task_save_demarche_dossiers_from_ds.delay(
                demarche.ds_number, using_updated_since=False
            )

    @admin.action(
        description="🗂️☁️ Rafraîchir les nouveaux dossiers ou les dossiers modifiés d’une démarche depuis DN depuis la dernière mise à jour"
    )
    def refresh_new_or_modified_dossiers_from_ds(self, request, queryset):
        for demarche in queryset:
            task_save_demarche_dossiers_from_ds.delay(
                demarche.ds_number, using_updated_since=True
            )

    def link_to_json(self, obj):
        return mark_safe(f'<a href="{obj.json_url}">JSON brut</a>')


@admin.register(PersonneMorale)
class PersonneMoraleAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address",)
    list_display = ("__str__", "siret")
    fieldsets = (
        (
            "Informations",
            {
                "fields": (
                    "siret",
                    "raison_sociale",
                    "address",
                    "siren",
                    "naf",
                    "forme_juridique",
                )
            },
        ),
    )
    search_fields = ("siret", "siren", "raison_sociale")


@admin.register(Dossier)
class DossierAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_filter = ("ds_state",)
    list_display = (
        "ds_number",
        "ds_state",
        "projet_intitule",
        "admin_projet_link",
        "link_to_json",
        "demande_categorie_detr",
    )

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "ds_id",
                    "ds_number",
                    "ds_state",
                    "ds_demandeur",
                    "admin_projet_link",
                    "app_projet_link",
                    "link_to_ds",
                )
            },
        ),
        (
            "Champs DN",
            {
                "classes": ("collapse", "open"),
                "fields": tuple(field.name for field in Dossier._MAPPED_CHAMPS_FIELDS),
            },
        ),
        (
            "Annotations DN",
            {
                "classes": ("collapse", "open"),
                "fields": tuple(
                    field.name for field in Dossier._MAPPED_ANNOTATIONS_FIELDS
                ),
            },
        ),
        (
            "Dates",
            {
                "classes": ("collapse", "open"),
                "fields": (
                    "ds_date_depot",
                    "ds_date_passage_en_construction",
                    "ds_date_passage_en_instruction",
                    "ds_date_traitement",
                    "ds_date_derniere_modification",
                    "ds_date_derniere_modification_champs",
                ),
            },
        ),
        (
            "Données brutes",
            {"classes": ("collapse", "open"), "fields": ("link_to_json",)},
        ),
    )
    actions = ("refresh_from_db", "refresh_from_ds")
    raw_id_fields = (
        "projet_adresse",
        "ds_demandeur",
    )
    search_fields = ("ds_number", "projet_intitule")
    readonly_fields = [field.name for field in Dossier._meta.fields] + [
        "admin_projet_link",
        "app_projet_link",
        "link_to_ds",
        "link_to_json",
    ]

    def perimetre(self, obj) -> int:
        return obj.get_projet_perimetre()

    perimetre.short_description = "Périmètre"

    @admin.action(description="🛢️ Rafraîchir depuis la base de données")
    def refresh_from_db(self, request, queryset):
        for dossier in queryset:
            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)

    @admin.action(description="☁️ Rafraîchir depuis DN")
    def refresh_from_ds(self, request, queryset):
        for dossier in queryset:
            task_save_one_dossier_from_ds.delay(dossier.ds_number)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = (
            qs.select_related(
                "ds_data__ds_demarche",
                "projet",
                "porteur_de_projet_arrondissement",
                "porteur_de_projet_arrondissement__core_arrondissement",
                "porteur_de_projet_arrondissement__core_arrondissement",
                "porteur_de_projet_departement",
            )
            .prefetch_related(
                "porteur_de_projet_arrondissement__core_arrondissement__departement",
            )
            .defer(
                "ds_data__raw_data",  # Main Dossier
                "ds_data__ds_demarche__raw_ds_data",  # Related Demarche
            )
        )
        return qs

    def link_to_json(self, obj):
        return mark_safe(f'<a href="{obj.json_url}">JSON brut</a>')

    def admin_projet_link(self, obj):
        return (
            mark_safe(
                f'<a href="{reverse("admin:gsl_projet_projet_change", args=[obj.projet.id])}">{obj.projet.id}</a>'
            )
            if obj.projet
            else None
        )

    admin_projet_link.short_description = "Projet"
    admin_projet_link.admin_order_field = "projet__id"

    def app_projet_link(self, obj):
        if obj.projet:
            url = reverse("projet:get-projet", args=[obj.projet.id])
            return mark_safe(f'<a href="{url}">Voir le projet ({obj.projet.id})</a>')
        return None

    app_projet_link.short_description = "Lien vers la page projet"
    app_projet_link.admin_order_field = "projet__id"

    def link_to_ds(self, obj):
        return mark_safe(
            f'<a href="{obj.url_on_ds}" target="_blank">Voir sur Démarche Numérique ({obj.ds_number})</a>'
        )

    link_to_ds.short_description = "Démarche Numérique"


@admin.register(FieldMappingForHuman)
class FieldMappingForHumanAdmin(
    AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin
):
    list_display = ("label", "django_field", "demarche__ds_number")
    resource_classes = (FieldMappingForHumanResource,)
    list_filter = ("demarche__ds_number",)
    readonly_fields = ("demarche",)
    search_fields = ("label", "django_field")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("demarche")
        return qs


@admin.register(FieldMappingForComputer)
class FieldMappingForComputerAdmin(
    AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin
):
    readonly_fields = [
        field.name
        for field in FieldMappingForComputer._meta.get_fields()
        if field.name != "django_field"
    ]
    list_display = (
        "ds_field_id",
        "ds_field_label",
        "ds_field_type",
        "django_field",
        "demarche__ds_number",
    )
    list_filter = ("demarche__ds_number", "ds_field_type")
    resource_classes = (FieldMappingForComputerResource,)
    search_fields = ("ds_field_label", "django_field", "ds_field_id")
    search_help_text = "Chercher par ID ou intitulé DN, ou par champ Django"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("demarche")
        return qs


@admin.register(Profile)
class ProfileAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    search_fields = ("ds_id", "ds_email")


class HasCoreArrondissementFilter(admin.SimpleListFilter):
    title = "Arrondissement INSEE complété"
    parameter_name = "has_insee_arr"

    def lookups(self, request, model_admin):
        return (
            ("y", "Oui"),
            ("n", "Non"),
        )

    def queryset(self, request, queryset):
        if self.value() == "y":
            return queryset.filter(
                core_arrondissement__isnull=False,
            )
        elif self.value() == "n":
            return queryset.filter(
                core_arrondissement__isnull=True,
            )


@admin.register(Arrondissement)
class ArrondissementAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("__str__", "core_arrondissement")
    list_filter = (HasCoreArrondissementFilter,)
    autocomplete_fields = ("core_arrondissement",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("core_arrondissement")
        return qs


class HasCoreDepartementFilter(admin.SimpleListFilter):
    title = "Département INSEE complété"
    parameter_name = "has_insee_dpt"

    def lookups(self, request, model_admin):
        return (
            ("y", "Oui"),
            ("n", "Non"),
        )

    def queryset(self, request, queryset):
        if self.value() == "y":
            return queryset.filter(
                core_departement__isnull=False,
            )
        elif self.value() == "n":
            return queryset.filter(
                core_departement__isnull=True,
            )


@admin.register(Departement)
class DepartementAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("__str__", "core_departement")
    list_filter = (HasCoreDepartementFilter,)
    autocomplete_fields = ("core_departement",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("core_departement")
        return qs


@admin.register(NaturePorteurProjet)
class NaturePorteurProjetAdmin(
    AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin
):
    list_display = ("__str__", "type", "dossiers_count")
    list_filter = ("type",)
    list_editable = ("type",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(dossier_count=Count("dossier"))

    def dossiers_count(self, obj) -> int:
        return obj.dossier_count

    dossiers_count.admin_order_field = "dossier_count"
    dossiers_count.short_description = "# de dossiers"


@admin.register(CategorieDetr)
class CategorieDetrAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "id",
        "departement",
        "label",
        "parent_label",
        "rank",
        "active",
        "deactivated_at",
        "dossiers_count",
    )
    readonly_fields = ("demarche", "departement", "label", "deactivated_at", "active")
    list_filter = (
        "departement",
        "active",
        "deactivated_at",
        "demarche__ds_number",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("demarche")
        qs = qs.annotate(dossier_count=Count("dossier"))
        return qs

    def dossiers_count(self, obj) -> int:
        return obj.dossier_count

    dossiers_count.admin_order_field = "dossier_count"
    dossiers_count.short_description = "# de dossiers"


@admin.register(CategorieDsil)
class CategorieDsilAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("id", "label", "rank", "active", "deactivated_at")
    readonly_fields = ("demarche", "label", "deactivated_at", "active")
    list_filter = ("demarche__ds_number", "active", "deactivated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("demarche")
        return qs


@admin.register(CritereEligibiliteDsil)
class CategorieDoperationAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("id", "label")


@admin.register(CritereEligibiliteDetr)
class CritereEligibiliteDetrAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("id", "label", "demarche__ds_number")
    readonly_fields = ("demarche", "demarche_revision", "detr_category", "label")
    list_filter = ("demarche__ds_number",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("demarche")
        return qs
