from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from import_export.admin import ImportMixin

from gsl_core.models import (
    Adresse,
    Arrondissement,
    Collegue,
    Commune,
    Departement,
    Region,
)

from .resources import ArrondissementResource, DepartementResource, RegionResource


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
class CollegueAdmin(UserAdmin, admin.ModelAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff")
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
            "Gestion des droits",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )


@admin.register(Adresse)
class AdresseAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("label", "postal_code", "commune")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("commune")
        return queryset


@admin.register(Region)
class RegionAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    resource_classes = (RegionResource,)


@admin.register(Departement)
class DepartementAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    resource_classes = (DepartementResource,)


@admin.register(Arrondissement)
class ArrondissementAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    resource_classes = (ArrondissementResource,)


@admin.register(Commune)
class CoreModelAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    pass


admin.site.unregister(Group)
