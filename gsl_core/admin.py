from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.db.models import Count
from import_export.admin import ImportMixin

from gsl_core.models import (
    Adresse,
    Arrondissement,
    Collegue,
    Commune,
    Departement,
    Perimetre,
    Region,
)
from gsl_core.tasks import associate_or_update_ds_profile_to_users

from .resources import (
    ArrondissementResource,
    CommuneResource,
    DepartementResource,
    RegionResource,
)


class AllPermsForStaffUser:
    def has_module_permission(self, request):
        return request.user.is_staff or request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(Collegue)
class CollegueAdmin(AllPermsForStaffUser, UserAdmin, admin.ModelAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "perimetre",
        "last_login",
        "ds_profile",
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Informations personnelles", {"fields": ("first_name", "last_name", "email")}),
        (
            "ProConnect",
            {
                "fields": (
                    "proconnect_sub",
                    "proconnect_uid",
                    "proconnect_idp_id",
                    "proconnect_siret",
                    "proconnect_chorusdt",
                )
            },
        ),
        (
            "Démarche Numérique",
            {"fields": ("ds_profile",)},
        ),
        (
            "Gestion des droits",
            {
                "fields": ("is_active", "is_staff", "is_superuser", "perimetre"),
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    autocomplete_fields = ["perimetre", "ds_profile"]
    actions = ("associate_ds_profile_to_users",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("perimetre__departement", "perimetre__region")

    @admin.action(description="Association des profils DN aux utilisateurs")
    def associate_ds_profile_to_users(self, request, queryset):
        user_ids = list(queryset.values_list("id", flat=True))
        associate_or_update_ds_profile_to_users(user_ids)


@admin.register(Adresse)
class AdresseAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("label", "postal_code", "commune")
    autocomplete_fields = ("commune",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("commune")
        return queryset


@admin.register(Region)
class RegionAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    resource_classes = (RegionResource,)


@admin.register(Departement)
class DepartementAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    search_fields = ("name", "insee_code")
    resource_classes = (DepartementResource,)


@admin.register(Arrondissement)
class ArrondissementAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    search_fields = ("name", "insee_code")
    resource_classes = (ArrondissementResource,)


@admin.register(Commune)
class CommuneAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    resource_classes = (CommuneResource,)
    list_display = ("name", "insee_code", "departement", "arrondissement")
    list_filter = ("departement__region", "departement", "arrondissement")
    search_fields = (
        "name",
        "insee_code",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("arrondissement", "departement")
        return queryset


@admin.register(Perimetre)
class PerimetreAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    search_fields = (
        "departement__insee_code",
        "arrondissement__insee_code",
        "departement__name",
        "region__name",
        "arrondissement__name",
    )
    list_display = (
        "__str__",
        "type",
        "region_id",
        "departement_id",
        "arrondissement_id",
        "user_count",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("departement", "region")
        queryset = queryset.annotate(user_count=Count("collegue"))
        return queryset

    def user_count(self, obj):
        return obj.user_count

    user_count.admin_order_field = "user_count"
    user_count.short_description = "Nb d’utilisateurs"


admin.site.unregister(Group)
