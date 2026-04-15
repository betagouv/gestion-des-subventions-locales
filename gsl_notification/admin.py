from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe

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
        "dossier_link",
        "created_by",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("dossier_link",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related(
            "programmation_projet__dotation_projet__projet__dossier_ds"
        )
        return qs

    def dossier_link(self, obj):
        dossier = obj.programmation_projet.dotation_projet.projet.dossier_ds
        if dossier:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossier_change",
                args=[dossier.id],
            )
            return mark_safe(f'<a href="{url}">{dossier.ds_number}</a>')
        return None

    dossier_link.short_description = "Dossier"
    dossier_link.admin_order_field = (
        "programmation_projet__dotation_projet__projet__dossier_ds__ds_number"
    )


@admin.register(LettreNotification)
class LettreNotificationAdmin(ArreteAdmin):
    pass


@admin.action(description="Relancer l'analyse antivirus")
def relaunch_antivirus_scan(modeladmin, request, queryset):
    for instance in queryset:
        file_field_name = "logo" if hasattr(instance, "logo") else "file"
        scan_uploaded_document.delay(instance._meta.label, instance.pk, file_field_name)
    modeladmin.message_user(
        request,
        f"{queryset.count()} analyse(s) antivirus relancée(s).",
    )


@admin.register(ArreteEtLettreSignes)
class ArreteEtLettreSignesAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "__str__",
        "dossier_link",
        "file",
        "created_by",
        "created_at",
        "last_scan",
        "is_infected",
    )
    readonly_fields = (
        "dossier_link",
        "last_scan",
        "is_infected",
    )
    actions = [relaunch_antivirus_scan]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related(
            "programmation_projet__dotation_projet__projet__dossier_ds"
        )
        return qs

    def dossier_link(self, obj):
        dossier = obj.programmation_projet.dotation_projet.projet.dossier_ds
        if dossier:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossier_change",
                args=[dossier.id],
            )
            return mark_safe(f'<a href="{url}">{dossier.ds_number}</a>')
        return None

    dossier_link.short_description = "Dossier"
    dossier_link.admin_order_field = (
        "programmation_projet__dotation_projet__projet__dossier_ds__ds_number"
    )


@admin.register(Annexe)
class AnnexeAdmin(ArreteEtLettreSignesAdmin):
    pass


@admin.register(ModeleArrete)
class ModeleArreteAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("pk", "name", "perimetre", "created_by", "last_scan", "is_infected")
    list_filter = ("perimetre__region__name", "perimetre__departement__name")
    readonly_fields = ("last_scan", "is_infected")
    actions = [relaunch_antivirus_scan]

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
