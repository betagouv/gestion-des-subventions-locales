from django.contrib import admin, messages
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from import_export.admin import ImportExportMixin

from gsl_core.admin import AllPermsForStaffUser
from gsl_core.models import Arrondissement

from .forms import RefreshDossiersDepotForm
from .models import (
    CategorieDetr,
    CategorieDsil,
    Demarche,
    Dossier,
    DossierData,
    FieldMapping,
    NaturePorteurProjet,
    PersonneMorale,
    Profile,
)
from .resources import FieldMappingResource
from .tasks import (
    task_refresh_dossier_from_saved_data,
    task_refresh_field_mappings_from_demarche_data,
    task_save_demarche_dossiers_from_ds,
    task_save_demarche_from_ds,
    task_save_one_dossier_from_ds,
)


@admin.register(Demarche)
class DemarcheAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    change_list_template = "admin/gsl_demarches_simplifiees/demarche/change_list.html"
    readonly_fields = tuple(
        field.name
        for field in Demarche._meta.get_fields()
        if field.name not in ("raw_ds_data")
    )
    list_display = (
        "ds_number",
        "ds_title",
        "date_de_derniere_mise_a_jour",
        "ds_state",
        "dossiers_count",
        "fields_count",
        "link_to_json",
    )
    actions = (
        "save_demarche_from_ds",
        "refresh_field_mappings",
        "refresh_dossiers_from_ds",
        "refresh_new_or_modified_dossiers_from_ds",
    )
    fieldsets = (
        (None, {"fields": ("ds_number", "ds_id", "ds_title", "ds_state")}),
        (
            "Dates",
            {
                "fields": (
                    "ds_date_creation",
                    "ds_date_fermeture",
                    "active_revision_date",
                    "active_revision_id",
                    "updated_since",
                )
            },
        ),
        (
            "Instructeurs",
            {
                "fields": ("ds_instructeurs",),
            },
        ),
        (
            "Données brutes",
            {
                "fields": ("raw_ds_data",),
                "classes": ("collapse", "open"),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.defer("raw_ds_data")
        return qs.annotate(dossiers_count=Count("dossierdata"))

    def dossiers_count(self, obj) -> int:
        return obj.dossiers_count

    dossiers_count.admin_order_field = "dossiers_count"
    dossiers_count.short_description = "# de dossiers"

    def fields_count(self, obj) -> int:
        return obj.fieldmapping_set.count()

    fields_count.admin_order_field = "fields_count"
    fields_count.short_description = "# de champs"

    def date_de_derniere_mise_a_jour(self, obj) -> str:
        return (
            timezone.localtime(obj.updated_since).strftime("%d/%m/%Y %H:%M")
            if obj.updated_since
            else ""
        )

    date_de_derniere_mise_a_jour.admin_order_field = "updated_since"
    date_de_derniere_mise_a_jour.short_description = "Date de dernière mise à jour"

    @admin.action(
        description="🔍🛢️ Rafraîchir les correspondances de champs depuis les données sauvegardées"
    )
    def refresh_field_mappings(self, request, queryset):
        for demarche in queryset:
            task_refresh_field_mappings_from_demarche_data(demarche.ds_number)

    @admin.action(description="📃☁️ Rafraîchir la démarche depuis DN")
    def save_demarche_from_ds(self, request, queryset):
        for demarche in queryset:
            task_save_demarche_from_ds(demarche.ds_number)

    @admin.action(
        description="🗂️☁️ Rafraîchir tous les dossiers de la démarche depuis DN"
    )
    def refresh_dossiers_from_ds(self, request, queryset):
        for demarche in queryset:
            task_save_demarche_dossiers_from_ds.delay(
                demarche.ds_number, using_updated_since=False
            )

    @admin.action(
        description="🗂️☁️ Rafraîchir les nouveaux dossiers ou les dossiers modifiés d’une démarche depuis DN depuis la dernière mise à jour"
    )
    def refresh_new_or_modified_dossiers_from_ds(self, request, queryset):
        for demarche in queryset:
            task_save_demarche_dossiers_from_ds.delay(
                demarche.ds_number, using_updated_since=True
            )

    def link_to_json(self, obj):
        return mark_safe(f'<a href="{obj.json_url}">JSON brut</a>')

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "refresh-dossiers-depot/",
                self.admin_site.admin_view(self.refresh_dossiers_depot_view),
                name="gsl_demarches_simplifiees_demarche_refresh_dossiers_depot",
            ),
        ]
        return custom + urls

    def refresh_dossiers_depot_view(self, request):
        if request.method == "POST":
            form = RefreshDossiersDepotForm(request.POST)
            if form.is_valid():
                demarche = form.cleaned_data["demarche"]
                updated_after = form.cleaned_data["updated_after"]
                task_save_demarche_dossiers_from_ds.delay(
                    demarche.ds_number,
                    using_updated_since=False,
                    updated_after_iso=updated_after.isoformat(),
                )
                self.message_user(
                    request,
                    f"Rafraîchissement des dossiers de la démarche « {demarche.ds_title} » "
                    f"déposés après le {timezone.localtime(updated_after).strftime('%d/%m/%Y à %H:%M')} "
                    "en cours (tâche Celery).",
                    messages.SUCCESS,
                )
                return redirect("admin:gsl_demarches_simplifiees_demarche_changelist")
        else:
            form = RefreshDossiersDepotForm()
        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "opts": self.model._meta,
            "title": "Rafraîchir les dossiers déposés/modifiés après une date",
        }
        return render(
            request,
            "admin/gsl_demarches_simplifiees/demarche/refresh_dossiers_depot.html",
            context,
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["refresh_dossiers_depot_url"] = reverse(
            "admin:gsl_demarches_simplifiees_demarche_refresh_dossiers_depot"
        )
        return super().changelist_view(request, extra_context)


@admin.register(PersonneMorale)
class PersonneMoraleAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    raw_id_fields = ("address",)
    list_display = ("__str__", "siret")
    fieldsets = (
        (
            "Informations",
            {
                "fields": (
                    "siret",
                    "raison_sociale",
                    "address",
                    "siren",
                    "naf",
                    "forme_juridique",
                )
            },
        ),
    )
    search_fields = ("siret", "siren", "raison_sociale")


class ArrondissementFilter(admin.SimpleListFilter):
    title = "Arrondissement"
    parameter_name = "arrondissement"

    def lookups(self, request, model_admin):
        departement_id = request.GET.get("perimetre__departement__insee_code__exact")

        if not departement_id:
            return []  # Aucun arrondissement tant que département non choisi

        arrondissements = Arrondissement.objects.filter(
            departement__pk=departement_id
        ).order_by("insee_code")

        return [(a.insee_code, (f"{a.pk} - {a.name}")) for a in arrondissements]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(perimetre__arrondissement__pk=self.value())
        return queryset


@admin.register(Dossier)
class DossierAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_filter = ("ds_state",)
    list_display = (
        "ds_number",
        "ds_state",
        "projet_intitule",
        "departement",
        "admin_projet_link",
        "link_to_json",
    )

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "ds_id",
                    "ds_number",
                    "ds_state",
                    "ds_demandeur",
                    "admin_projet_link",
                    "app_projet_link",
                    "link_to_ds",
                )
            },
        ),
        (
            "Champs DN",
            {
                "classes": ("collapse", "open"),
                "fields": tuple(field.name for field in Dossier._MAPPED_CHAMPS_FIELDS),
            },
        ),
        (
            "Annotations DN",
            {
                "classes": ("collapse", "open"),
                "fields": tuple(
                    field.name for field in Dossier._MAPPED_ANNOTATIONS_FIELDS
                ),
            },
        ),
        (
            "Dates",
            {
                "classes": ("collapse", "open"),
                "fields": (
                    "ds_date_depot",
                    "ds_date_passage_en_construction",
                    "ds_date_passage_en_instruction",
                    "ds_date_traitement",
                    "ds_date_derniere_modification",
                    "ds_date_derniere_modification_champs",
                ),
            },
        ),
        (
            "Données brutes",
            {
                "classes": ("collapse", "open"),
                "fields": ("link_to_json", "link_to_edit_dossier_data"),
            },
        ),
    )
    actions = ("refresh_from_db", "refresh_from_ds")
    raw_id_fields = (
        "projet_adresse",
        "ds_demandeur",
    )
    search_fields = ("ds_number", "projet_intitule")
    list_filter = ("ds_state", ArrondissementFilter, "perimetre__departement")
    readonly_fields = [field.name for field in Dossier._meta.fields] + [
        "admin_projet_link",
        "app_projet_link",
        "link_to_ds",
        "link_to_json",
        "link_to_edit_dossier_data",
    ]

    @admin.action(description="🛢️ Rafraîchir depuis la base de données")
    def refresh_from_db(self, request, queryset):
        for dossier in queryset:
            task_refresh_dossier_from_saved_data.delay(dossier.ds_number)

    @admin.action(description="☁️ Rafraîchir depuis DN")
    def refresh_from_ds(self, request, queryset):
        for dossier in queryset:
            task_save_one_dossier_from_ds.delay(dossier.ds_number)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related(
            "ds_data__ds_demarche",
            "projet",
            "perimetre__departement",
        ).defer(
            "ds_data__raw_data",  # Main Dossier
            "ds_data__ds_demarche__raw_ds_data",  # Related Demarche
        )
        return qs

    def link_to_json(self, obj):
        return mark_safe(f'<a href="{obj.json_url}">JSON brut</a>')

    def link_to_edit_dossier_data(self, obj):
        if obj.ds_data_id:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossierdata_change",
                args=[obj.ds_data_id],
            )
            return mark_safe(
                f'<a href="{url}">Modifier les données brutes (dossierData)</a>'
            )
        return None

    link_to_edit_dossier_data.short_description = "Données brutes DN"

    def admin_projet_link(self, obj):
        return (
            mark_safe(
                f'<a href="{reverse("admin:gsl_projet_projet_change", args=[obj.projet.id])}">{obj.projet.id}</a>'
            )
            if obj.projet
            else None
        )

    admin_projet_link.short_description = "Projet"
    admin_projet_link.admin_order_field = "projet__id"

    def app_projet_link(self, obj):
        if obj.projet:
            url = reverse("projet:get-projet", args=[obj.projet.id])
            return mark_safe(f'<a href="{url}">Voir le projet ({obj.projet.id})</a>')
        return None

    app_projet_link.short_description = "Lien vers la page projet"
    app_projet_link.admin_order_field = "projet__id"

    def link_to_ds(self, obj):
        return mark_safe(
            f'<a href="{obj.url_on_ds}" target="_blank">Voir sur Démarche Numérique ({obj.ds_number})</a>'
        )

    link_to_ds.short_description = "Démarche Numérique"

    def departement(self, obj):
        if obj.perimetre is None:
            return None
        return obj.perimetre.departement.insee_code

    departement.admin_order_field = "perimetre__departement__insee_code"
    departement.short_description = "Département"


@admin.register(DossierData)
class DossierDataAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = (
        "id",
        "dossier__projet_intitule",
        "link_to_dossier",
    )
    search_fields = ("dossier__ds_number",)
    readonly_fields = ("link_to_dossier",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("dossier")

    fieldsets = ((None, {"fields": ("link_to_dossier", "raw_data")}),)

    def link_to_dossier(self, obj):
        dossier = getattr(obj, "dossier", None)
        if dossier:
            url = reverse(
                "admin:gsl_demarches_simplifiees_dossier_change",
                args=[dossier.id],
            )
            return mark_safe(
                f'<a href="{url}">Voir le dossier #{dossier.ds_number}</a>'
            )
        return None

    link_to_dossier.short_description = "Dossier"


@admin.register(FieldMapping)
class FieldMappingAdmin(AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin):
    readonly_fields = [
        field.name
        for field in FieldMapping._meta.get_fields()
        if field.name != "django_field"
    ]
    list_display = (
        "ds_field_id",
        "ds_field_label",
        "ds_field_type",
        "django_field",
        "demarche__ds_number",
    )
    list_filter = ("demarche__ds_number", "ds_field_type")
    resource_classes = (FieldMappingResource,)
    search_fields = ("ds_field_label", "django_field", "ds_field_id")
    search_help_text = "Chercher par ID ou intitulé DN, ou par champ Django"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("demarche").defer("demarche__raw_ds_data")
        return qs


@admin.register(Profile)
class ProfileAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    search_fields = ("ds_id", "ds_email")


@admin.register(NaturePorteurProjet)
class NaturePorteurProjetAdmin(
    AllPermsForStaffUser, ImportExportMixin, admin.ModelAdmin
):
    list_display = ("__str__", "type", "dossiers_count")
    list_filter = ("type",)
    list_editable = ("type",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(dossiers_count=Count("dossier"))

    def dossiers_count(self, obj) -> int:
        return obj.dossiers_count

    dossiers_count.admin_order_field = "dossiers_count"
    dossiers_count.short_description = "# de dossiers"


@admin.register(CategorieDsil)
class CategorieDsilAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("id", "label", "rank", "active", "deactivated_at", "dossiers_count")
    readonly_fields = ("demarche", "label", "deactivated_at", "active")
    list_filter = ("demarche__ds_number", "active", "deactivated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(dossiers_count=Count("dossier"))

    def dossiers_count(self, obj) -> int:
        return obj.dossiers_count

    dossiers_count.admin_order_field = "dossiers_count"
    dossiers_count.short_description = "# de dossiers"


@admin.register(CategorieDetr)
class CategorieDetrAdmin(CategorieDsilAdmin):
    list_display = (
        "id",
        "departement",
        "label",
        "parent_label",
        "rank",
        "active",
        "deactivated_at",
        "dossiers_count",
    )
    readonly_fields = (
        "demarche",
        "departement",
        "label",
        "deactivated_at",
        "active",
        "dossiers_count",
    )
    list_filter = (
        "departement",
        "active",
        "deactivated_at",
        "demarche__ds_number",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("departement")
        return qs.annotate(dossiers_count=Count("dossier"))
