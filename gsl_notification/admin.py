from django.contrib import admin

from gsl_core.admin import AllPermsForStaffUser

from .models import (
    Annexe,
    Arrete,
    ArreteEtLettreSignes,
    LettreNotification,
    ModeleArrete,
    ModeleLettreNotification,
)


@admin.register(ModeleArrete)
class ModeleArreteAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("__str__", "perimetre", "created_by")


@admin.register(ModeleLettreNotification)
class ModeleLettreNotificationAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("__str__", "perimetre", "created_by")


@admin.register(Arrete)
class ArreteAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "projet",
        "dotation",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(LettreNotification)
class LettreNotificationAdmin(ArreteAdmin):
    pass


@admin.register(ArreteEtLettreSignes)
class ArreteEtLettreSignesAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "projet",
        "dotation",
        "file",
        "created_by",
        "created_at",
    )


@admin.register(Annexe)
class AnnexeAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "projet",
        "file",
        "created_by",
        "created_at",
    )
