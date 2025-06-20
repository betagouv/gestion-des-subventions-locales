from django.contrib import admin

from gsl_core.admin import AllPermsForStaffUser

from .models import ArreteSigne


@admin.register(ArreteSigne)
class ArreteSigneAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "programmation_projet",
        "file",
        "created_by",
        "created_at",
    )
