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
from .tasks import scan_uploaded_document


@admin.register(Arrete)
class ArreteAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "programmation_projet",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(LettreNotification)
class LettreNotificationAdmin(ArreteAdmin):
    pass


@admin.action(description="Relancer l'analyse antivirus")
def relaunch_antivirus_scan(modeladmin, request, queryset):
    for instance in queryset:
        scan_uploaded_document.delay(instance._meta.label, instance.pk)
    modeladmin.message_user(
        request,
        f"{queryset.count()} analyse(s) antivirus relancée(s).",
    )


@admin.register(ArreteEtLettreSignes)
class ArreteEtLettreSignesAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "programmation_projet",
        "file",
        "created_by",
        "created_at",
        "last_scan",
        "is_infected",
    )
    readonly_fields = ("last_scan", "is_infected")
    actions = [relaunch_antivirus_scan]


@admin.register(Annexe)
class AnnexeAdmin(ArreteEtLettreSignesAdmin):
    pass


@admin.register(ModeleArrete)
class ModeleArreteAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("pk", "name", "perimetre", "created_by")
    list_filter = ("perimetre__region__name", "perimetre__departement__name")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related(
            "perimetre",
            "perimetre__region",
            "perimetre__departement",
            "perimetre__arrondissement",
            "created_by",
        )
        return qs


@admin.register(ModeleLettreNotification)
class ModeleLettreNotificationAdmin(ModeleArreteAdmin):
    pass
