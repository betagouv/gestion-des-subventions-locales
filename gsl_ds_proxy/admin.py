from django.contrib import admin, messages

from gsl_ds_proxy.models import ProxyToken


@admin.register(ProxyToken)
class ProxyTokenAdmin(admin.ModelAdmin):
    list_display = ("label", "demarche", "is_active", "created_at", "instructeur_count")
    list_filter = ("is_active", "demarche")
    readonly_fields = ("key_hash", "created_at", "updated_at")
    filter_horizontal = ("instructeurs",)

    def instructeur_count(self, obj):
        return obj.instructeurs.count()

    instructeur_count.short_description = "Nb instructeurs"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        plaintext = getattr(obj, "_plaintext_key", None)
        if plaintext:
            messages.success(
                request,
                f"Clé API générée (à copier maintenant, elle ne sera plus affichée) : {plaintext}",
            )
