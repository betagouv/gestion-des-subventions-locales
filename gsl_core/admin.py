from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from gsl_core.models import (
    Adresse,
    Arrondissement,
    Collegue,
    Commune,
    Departement,
    Region,
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
class CollegueAdmin(UserAdmin):
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


@admin.register(Commune)
@admin.register(Arrondissement)
@admin.register(Departement)
@admin.register(Region)
class CoreModelAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    pass


admin.site.unregister(Group)
