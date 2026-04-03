from django.contrib import admin

from gsl_ds_proxy.models import ProxyToken


@admin.register(ProxyToken)
class ProxyTokenAdmin(admin.ModelAdmin):
    list_display = ("label", "is_active", "created_at", "instructeur_count")
    list_filter = ("is_active",)
    readonly_fields = ("key", "created_at", "updated_at")
    filter_horizontal = ("instructeurs",)

    def instructeur_count(self, obj):
        return obj.instructeurs.count()

    instructeur_count.short_description = "Nb instructeurs"
