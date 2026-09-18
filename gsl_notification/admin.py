from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe

from gsl_core.admin import AllPermsForStaffUser

from .models import (
    Annexe,
    Arrete,
    DocumentImportJob,
    LettreEtArreteSignes,
    LettreNotification,
    LettreRefus,
    LettreRefusSignee,
    ModeleArrete,
    ModeleLettreNotification,
    ModeleLettreRefus,
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
    list_select_related = ("enveloppe_projet__projet__dossier_ds",)

    def dossier_link(self, obj):
        dossier = obj.enveloppe_projet.projet.dossier_ds
        if dossier:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossier_change",
                args=[dossier.id],
            )
            return mark_safe(f'<a href="{url}">{dossier.ds_number}</a>')
        return None

    dossier_link.short_description = "Dossier"
    dossier_link.admin_order_field = "enveloppe_projet__projet__dossier_ds__ds_number"


@admin.register(LettreNotification)
class LettreNotificationAdmin(ArreteAdmin):
    pass


@admin.register(LettreRefus)
class LettreRefusAdmin(ArreteAdmin):
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


@admin.register(LettreEtArreteSignes)
class LettreEtArreteSignesAdmin(AllPermsForStaffUser, admin.ModelAdmin):
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
    list_select_related = ("enveloppe_projet__projet__dossier_ds",)

    def dossier_link(self, obj):
        dossier = obj.enveloppe_projet.projet.dossier_ds
        if dossier:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossier_change",
                args=[dossier.id],
            )
            return mark_safe(f'<a href="{url}">{dossier.ds_number}</a>')
        return None

    dossier_link.short_description = "Dossier"
    dossier_link.admin_order_field = "enveloppe_projet__projet__dossier_ds__ds_number"


@admin.register(Annexe)
class AnnexeAdmin(LettreEtArreteSignesAdmin):
    pass


@admin.register(LettreRefusSignee)
class LettreRefusSigneeAdmin(LettreEtArreteSignesAdmin):
    pass


@admin.register(ModeleArrete)
class ModeleArreteAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("pk", "name", "perimetre", "created_by", "last_scan", "is_infected")
    list_filter = ("perimetre__region__name", "perimetre__departement__name")
    readonly_fields = ("last_scan", "is_infected")
    actions = [relaunch_antivirus_scan]
    list_select_related = (
        "perimetre",
        "perimetre__region",
        "perimetre__departement",
        "perimetre__arrondissement",
        "created_by",
    )


@admin.register(ModeleLettreNotification)
class ModeleLettreNotificationAdmin(ModeleArreteAdmin):
    pass


@admin.register(ModeleLettreRefus)
class ModeleLettreRefusAdmin(ModeleArreteAdmin):
    pass


@admin.register(DocumentImportJob)
class DocumentImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "file_count",
        "progress_display",
        "remove_qr_code",
        "created_by",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("created_by__email",)
    raw_id_fields = ("created_by",)
    readonly_fields = (
        "id",
        "created_by",
        "status",
        "s3_keys",
        "file_count",
        "total_pages",
        "processed_pages",
        "progress_display",
        "result",
        "remove_qr_code",
        "created_at",
        "updated_at",
    )
    fields = (
        "id",
        "created_by",
        "status",
        "s3_keys",
        "file_count",
        "total_pages",
        "processed_pages",
        "progress_display",
        "result",
        "remove_qr_code",
        "created_at",
        "updated_at",
    )
    list_select_related = ("created_by",)

    def has_add_permission(self, request):
        # Jobs are created by the import flow, never by hand.
        return False

    def progress_display(self, obj):
        return f"{obj.processed_pages} / {obj.total_pages}"

    progress_display.short_description = "Avancement"
