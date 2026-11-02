from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse

from gsl.core.admin import AllPermsForStaffUser

from .forms import ImportChorusFileForm
from .models import SuiviFinancier


@admin.register(SuiviFinancier)
class SuiviFinancierAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "ej",
        "dn",
        "dotation",
        "montant",
        "tv",
        "type_montant",
        "date_transaction",
        "date_engagement",
    )
    list_filter = ("dotation", "tv", "type_montant")
    search_fields = ("ej", "dn")

    # Lines only come from Chorus imports.
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "import-chorus/",
                self.admin_site.admin_view(self.import_chorus_view),
                name="gsl_chorus_suivifinancier_import_chorus",
            ),
        ]
        return custom + urls

    def import_chorus_view(self, request):
        if request.method == "POST":
            form = ImportChorusFileForm(request.POST, request.FILES)
            if form.is_valid():
                form.save()
                self.message_user(
                    request,
                    f"Import du fichier « {form.cleaned_data['file'].name} » "
                    "en cours (tâche Celery).",
                    messages.SUCCESS,
                )
                return redirect("admin:gsl_chorus_suivifinancier_changelist")
        else:
            form = ImportChorusFileForm()
        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "opts": self.model._meta,
            "title": "Importer un fichier Chorus",
        }
        return render(
            request,
            "admin/gsl_chorus/suivifinancier/import_chorus.html",
            context,
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_chorus_url"] = reverse(
            "admin:gsl_chorus_suivifinancier_import_chorus"
        )
        return super().changelist_view(request, extra_context)
