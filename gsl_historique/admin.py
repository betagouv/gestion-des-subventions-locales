from django.contrib import admin
from django.contrib.admin.models import ADDITION, CHANGE, DELETION
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.safestring import mark_safe

from gsl_core.models import Collegue
from gsl_historique.models import CollegueLogEntry, ProjetAction


@admin.register(ProjetAction)
class ProjetActionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "projet",
        "action_type",
        "dotation",
        "actor",
        "source",
    )
    list_filter = ("action_type", "source", "dotation")
    search_fields = ("projet__dossier_ds__ds_number",)
    readonly_fields = (
        "projet",
        "action_type",
        "created_at",
        "actor",
        "source",
        "dotation",
        "status",
        "euro_field_value",
        "document_name",
        "boolean_field",
        "boolean_value",
        "form_id",
    )
    ordering = ("-created_at",)


@admin.register(CollegueLogEntry)
class CollegueLogEntryAdmin(admin.ModelAdmin):
    list_display = (
        "action_time",
        "user",
        "collegue_link",
        "action_label",
        "change_message",
    )
    list_filter = ("action_flag", "action_time")
    search_fields = ("object_repr", "user__username", "user__email", "change_message")
    date_hierarchy = "action_time"
    readonly_fields = (
        "action_time",
        "user",
        "content_type",
        "object_id",
        "object_repr",
        "action_flag",
        "change_message",
    )

    def has_module_permission(self, request):
        return request.user.is_staff or request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff or request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        collegue_ct = ContentType.objects.get_for_model(Collegue)
        return (
            super()
            .get_queryset(request)
            .filter(content_type=collegue_ct)
            .select_related("user", "content_type")
        )

    def action_label(self, obj):
        return {ADDITION: "Ajout", CHANGE: "Modification", DELETION: "Suppression"}.get(
            obj.action_flag, "?"
        )

    action_label.short_description = "Action"

    def collegue_link(self, obj):
        try:
            url = reverse("admin:gsl_core_collegue_change", args=[obj.object_id])
            return mark_safe(f"<a href='{url}'>{obj.object_repr}</a>")
        except Exception:
            return obj.object_repr

    collegue_link.short_description = "Collègue"
    collegue_link.admin_order_field = "object_repr"
