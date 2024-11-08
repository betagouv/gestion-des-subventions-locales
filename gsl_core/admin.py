from django.contrib import admin
from django.contrib.auth.models import Group

from gsl_core.models import Arrondissement, Collegue, Commune, Departement, Region


@admin.register(Collegue)
class CollegueAdmin(admin.ModelAdmin):
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


admin.site.register(Commune)
admin.site.register(Arrondissement)
admin.site.register(Departement)
admin.site.register(Region)
admin.site.unregister(Group)
