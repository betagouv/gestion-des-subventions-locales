import logging
from io import BytesIO

import openpyxl
import tablib
from django import forms
from django.contrib import admin
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models, transaction
from django.db.models import Count, OuterRef, Subquery
from django.urls import reverse
from django.utils.safestring import mark_safe
from import_export.admin import ImportMixin
from import_export.formats.base_formats import CSV
from import_export.forms import ImportForm

from gsl_core.admin_alerts import notify_admins
from gsl_core.models import (
    Adresse,
    Arrondissement,
    Collegue,
    Commune,
    Departement,
    Perimetre,
    Region,
)
from gsl_core.tasks import associate_or_update_ds_profile_to_users
from gsl_simulation.models import Simulation

from .resources import (
    ArrondissementResource,
    CollegueResource,
    CommuneResource,
    DepartementResource,
    RegionResource,
)

logger = logging.getLogger(__name__)


class CollegueImportForm(ImportForm):
    """Custom import form that hides the format field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hide the format field by removing it from visible fields
        if "format" in self.fields:
            self.fields["format"].widget = self.fields["format"].hidden_widget()
            self.fields["format"].label = ""
            # Set default to CSV (index 0)
            self.fields["format"].initial = 0


class AllPermsForStaffUser:
    def has_module_permission(self, request):
        return request.user.is_staff or request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


class AllPermsForSuperUserAndViewOnlyForStaffUser:
    def has_module_permission(self, request):
        return request.user.is_staff or request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Collegue)
class CollegueAdmin(AllPermsForStaffUser, ImportMixin, UserAdmin, admin.ModelAdmin):
    resource_classes = (CollegueResource,)
    import_template_name = "admin/gsl_core/collegue/import.html"

    search_fields = (
        "username",
        "first_name",
        "last_name",
        "email",
        "perimetre__departement__insee_code",
    )

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff_custom",
        "is_superuser_custom",
        "perimetre_type",
        "perimetre_custom",
        "last_login",
        "last_simulation_created_in_perimetre",
        "comment",
        "dn_profile",
        "history_link",
    )

    list_editable = ("comment",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "comment":
            kwargs["widget"] = forms.Textarea(
                attrs={
                    "rows": 1,
                    "cols": 40,
                    "style": "resize: vertical; min-height: 1.5em;",
                }
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "last_login",
        "perimetre__departement",
        "perimetre__region",
    )

    def get_import_formats(self):
        """
        Override to return only CSV format.

        Excel files (.xlsx/.xls) are automatically preprocessed to CSV by import_action(),
        so only CSV format is needed.
        """

        return [CSV]

    def get_import_form_class(self, request):
        """Use custom form that hides the format field."""
        return CollegueImportForm

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Informations personnelles",
            {"fields": ("first_name", "last_name", "email", "comment")},
        ),
        (
            "ProConnect",
            {
                "fields": (
                    "proconnect_sub",
                    "proconnect_uid",
                    "proconnect_idp_id",
                    "proconnect_siret",
                    "proconnect_chorusdt",
                )
            },
        ),
        (
            "Démarche Numérique",
            {"fields": ("ds_profile",)},
        ),
        (
            "Gestion des droits",
            {
                "fields": ("is_active", "is_staff", "is_superuser", "perimetre"),
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    autocomplete_fields = ["perimetre", "ds_profile"]
    actions = ("associate_ds_profile_to_users", "deactivate_users", "activate_users")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly += ["is_superuser", "is_staff"]
        return readonly

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        actor = request.user
        # Cas création
        if not change:
            if obj.is_staff or obj.is_superuser:
                notify_admins(
                    f"Création d'utilisateur admin : {obj.username}",
                    (
                        f"Créé par {actor} ({actor.email}).\n"
                        f"Emai  : {obj.email}\n"
                        f"Statut équipe : {obj.is_staff}\n"
                        f"Statut super-utilisateur : {obj.is_superuser}"
                    ),
                )
            if obj.perimetre is not None:
                notify_admins(
                    "Création d'utilisateur",
                    f"Créé par {actor} ({actor.email}).\n"
                    f"Emai  : {obj.email}\n"
                    f"Perimètre : {obj.perimetre}",
                )
            return
        # Cas modification
        for flag in ("is_staff", "is_superuser"):
            if flag in form.changed_data and getattr(obj, flag):
                notify_admins(
                    f"Droit {flag} octroyé à {obj.email} ({obj.username})",
                    f"Octroyé par {actor} ({actor.email}).",
                )
        if "ds_profile" in form.changed_data and obj.ds_profile_id:
            notify_admins(
                f"Profil DN associé à {obj.email} ({obj.username})",
                (
                    f"Associé par {actor} ({actor.email}).\n"
                    f"Profil DN : {obj.ds_profile.ds_email} (id={obj.ds_profile.ds_id})"
                ),
            )
        if "perimetre" in form.changed_data and obj.perimetre_id:
            notify_admins(
                f"Perimètre associé à {obj.email} ({obj.username})",
                (
                    f"Associé par {actor} ({actor.email}).\n"
                    f"Perimètre : {obj.perimetre.entity_name} (id={obj.perimetre_id})"
                ),
            )
        if "is_active" in form.changed_data and obj.is_active is True:
            notify_admins(
                f"Réactivation d'un utilisateur désactivé {obj.email} ({obj.username})",
                f"Modifié par {actor} ({actor.email}).\n",
            )

    def process_result(self, result, request):
        response = super().process_result(result, request)
        self._notify_admins_of_import(result, request)
        return response

    def _notify_admins_of_import(self, result, request):
        from import_export.results import RowResult

        new_ids = [
            r.object_id
            for r in result.rows
            if r.import_type == RowResult.IMPORT_TYPE_NEW and r.object_id
        ]
        updated_ids = [
            r.object_id
            for r in result.rows
            if r.import_type == RowResult.IMPORT_TYPE_UPDATE and r.object_id
        ]
        if not new_ids and not updated_ids:
            return

        users_by_id = {
            u.pk: u
            for u in Collegue.objects.filter(
                pk__in=new_ids + updated_ids
            ).select_related(
                "perimetre__region",
                "perimetre__departement",
                "perimetre__arrondissement",
            )
        }
        actor = request.user
        lines = [f"Action déclenchée par {actor} ({actor.email})."]
        if new_ids:
            lines.append(f"\nCréés ({len(new_ids)}) :")
            lines += [
                f"- {users_by_id[i].email} — {users_by_id[i].perimetre}"
                for i in new_ids
                if i in users_by_id
            ]
        if updated_ids:
            lines.append(f"\nMis à jour ({len(updated_ids)}) :")
            lines += [
                f"- {users_by_id[i].email}" for i in updated_ids if i in users_by_id
            ]
        notify_admins(
            f"Import groupé d'utilisateurs : {len(new_ids)} créé(s), {len(updated_ids)} mis à jour",
            "\n".join(lines),
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        last_simulation_subquery = (
            Simulation.objects.filter(
                models.Q(enveloppe__perimetre=OuterRef("perimetre"))
                | models.Q(
                    enveloppe__perimetre__region_id=OuterRef("perimetre__region_id"),
                    enveloppe__perimetre__departement_id__isnull=True,
                    enveloppe__perimetre__arrondissement_id__isnull=True,
                )
                | models.Q(
                    enveloppe__perimetre__region_id=OuterRef("perimetre__region_id"),
                    enveloppe__perimetre__departement_id=OuterRef(
                        "perimetre__departement_id"
                    ),
                    enveloppe__perimetre__arrondissement_id__isnull=True,
                )
            )
            .order_by("-created_at")
            .values("created_at")[:1]
        )

        return qs.select_related(
            "perimetre__departement",
            "perimetre__region",
            "perimetre__arrondissement",
            "ds_profile",
        ).annotate(
            _last_simulation_created_at=Subquery(last_simulation_subquery),
        )

    @admin.action(description="🔃 Association des profils DN aux utilisateurs")
    def associate_ds_profile_to_users(self, request, queryset):
        user_ids = list(queryset.values_list("id", flat=True))
        before = dict(
            Collegue.objects.filter(pk__in=user_ids).values_list("pk", "ds_profile_id")
        )
        associate_or_update_ds_profile_to_users(user_ids)
        newly_associated = (
            Collegue.objects.filter(pk__in=user_ids, ds_profile__isnull=False)
            .exclude(ds_profile_id__in=[v for v in before.values() if v is not None])
            .select_related("ds_profile")
        )
        newly_associated = [
            u for u in newly_associated if before.get(u.pk) != u.ds_profile_id
        ]
        if newly_associated:
            lines = "\n".join(
                f"- {u.username} ↔ {u.ds_profile.ds_email}" for u in newly_associated
            )
            notify_admins(
                f"Association DN groupée : {len(newly_associated)} utilisateur(s)",
                (
                    f"Action déclenchée par {request.user} ({request.user.email}).\n"
                    f"{lines}"
                ),
            )

    @admin.action(description="🚫 Désactivation des utilisateurs")
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="✅ Réactivation des utilisateurs")
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)

    def is_staff_custom(self, obj):
        return obj.is_staff

    is_staff_custom.short_description = "Equipe"
    is_staff_custom.boolean = True

    def is_superuser_custom(self, obj):
        return obj.is_superuser

    is_superuser_custom.short_description = "Super"
    is_superuser_custom.boolean = True

    def perimetre_custom(self, obj):
        if obj.perimetre is None:
            return None
        if obj.perimetre.arrondissement is not None:
            return f"{obj.perimetre.arrondissement.insee_code} - {obj.perimetre.arrondissement.name}"
        if obj.perimetre.departement is not None:
            return f"{obj.perimetre.departement.insee_code}"
        if obj.perimetre.region is not None:
            return obj.perimetre.region.name
        return obj.perimetre

    perimetre_custom.short_description = "Périmètre"
    perimetre_custom.admin_order_field = "perimetre__departement__insee_code"

    def perimetre_type(self, obj):
        if obj.perimetre is None:
            return None
        if obj.perimetre.arrondissement is not None:
            return "Arr"
        if obj.perimetre.departement is not None:
            return "Dpt"
        if obj.perimetre.region is not None:
            return "Rgn"

    perimetre_type.short_description = "Type"

    def departement(self, obj):
        if obj.perimetre is None:
            return None
        if obj.perimetre.departement is not None:
            return obj.perimetre.departement.name
        return None

    departement.short_description = "Département"
    departement.admin_order_field = "perimetre__departement__name"

    def last_simulation_created_in_perimetre(self, obj):
        return obj._last_simulation_created_at

    last_simulation_created_in_perimetre.short_description = (
        "Dernière simulation créée (périmètre)"
    )
    last_simulation_created_in_perimetre.admin_order_field = (
        "_last_simulation_created_at"
    )

    def dn_profile(self, obj):
        if obj.ds_profile is None:
            return None
        return mark_safe(
            f"<a href='{reverse('admin:gsl_demarches_simplifiees_profile_change', args=[obj.ds_profile.id])}'>{obj.ds_profile.id}</a>"
        )

    dn_profile.short_description = "Profil DN"
    dn_profile.admin_order_field = "ds_profile__id"

    def history_link(self, obj):
        url = (
            reverse("admin:admin_logentry_changelist")
            + f"?object_id={obj.pk}&content_type={ContentType.objects.get_for_model(Collegue).pk}"
        )
        return mark_safe(f"<a href='{url}'>Historique</a>")

    history_link.short_description = "Historique"

    @staticmethod
    def _normalize_department_code(dept_code) -> str:
        """
        Normalize department code to 2-character string with leading zero.

        Examples:
            1 -> '01'
            10 -> '10'
            10.0 -> '10' (Excel float values)
            '2A' -> '2A' (Corsica)
            '2B' -> '2B' (Corsica)
        """
        dept_str = str(dept_code).strip()

        # Handle Corsica special codes
        if dept_str.upper() in ("2A", "2B"):
            return dept_str.upper()

        # Handle numeric codes - pad with zero if needed
        # Convert through float first to handle Excel's numeric cells (e.g., 10.0)
        try:
            dept_float = float(dept_str)
            dept_int = int(dept_float)
            return f"{dept_int:02d}"
        except ValueError:
            # Non-numeric, return as-is
            return dept_str

    @staticmethod
    def _normalize_arrondissement_code(arr_code) -> str:
        """
        Normalize arrondissement code to string, handling Excel float values.

        Arrondissement INSEE codes are 3 digits (e.g., '011' for first arrondissement of department 01).

        Examples:
            11 -> '011'
            11.0 -> '011' (Excel float values)
            '011' -> '011' (already string with padding)
        """
        arr_str = str(arr_code).strip()

        # Try to convert through float→int to handle Excel floats (e.g., 11.0 → 11)
        # Then pad to 3 digits for proper arrondissement format
        try:
            arr_float = float(arr_str)
            arr_int = int(arr_float)
            # Arrondissement codes are typically 3 digits
            return f"{arr_int:03d}"
        except ValueError:
            # Non-numeric, return as-is (e.g., Corsica codes like '2A1')
            return arr_str

    @staticmethod
    def _is_valid_email(email) -> bool:
        """Check if value looks like an email (contains @)."""
        email_str = str(email).strip()
        return "@" in email_str and len(email_str) > 3

    def parse_excel_to_dataset(self, import_file):
        """
        Parse hierarchical Excel file into flat tabular data for import.

        Excel structure:
        - Row 2: Headers
        - Row 3+: Hierarchical data with merged cells:
            - Department section: (dept_code, dept_name, None, None, email, prenom, nom)
            - Department emails: (None, None, None, None, email, prenom, nom) - inherits department
            - Arrondissement section: (None, None, perimeter_name, arr_code, email, prenom, nom)
            - Arrondissement emails: (None, None, None, None, email, prenom, nom) - inherits arrondissement

        Returns:
            tablib.Dataset with columns: email, departement_code, arrondissement_code, first_name, last_name
        """
        wb = openpyxl.load_workbook(import_file, read_only=True)
        ws = wb.active

        dataset = tablib.Dataset()
        dataset.headers = [
            "email",
            "departement_code",
            "arrondissement_code",
            "first_name",
            "last_name",
        ]

        current_department = None
        current_arrondissement = None
        skipped_rows = []

        # Start from row 3 (rows 1-2 are headers)
        for row_idx, row in enumerate(
            ws.iter_rows(min_row=3, values_only=True), start=3
        ):
            dept_code = row[0] if len(row) > 0 else None
            perimetre_name = row[2] if len(row) > 2 else None
            arr_code = row[3] if len(row) > 3 else None
            email = row[4] if len(row) > 4 else None
            prenom = row[5] if len(row) > 5 else None
            nom = row[6] if len(row) > 6 else None

            # Update state: new department section
            if dept_code is not None:
                current_department = self._normalize_department_code(dept_code)
                current_arrondissement = None  # Reset to department-level
                logger.debug(
                    f"Row {row_idx}: New department section - {current_department}"
                )

            # Update state: new arrondissement section
            if perimetre_name and arr_code:
                current_arrondissement = self._normalize_arrondissement_code(arr_code)
                logger.debug(
                    f"Row {row_idx}: New arrondissement section - {current_arrondissement}"
                )

            # Emit flat row if email is valid
            if email and self._is_valid_email(email):
                email_clean = str(email).strip().lower()

                if current_department is None:
                    skipped_rows.append(
                        {
                            "row": row_idx,
                            "email": email_clean,
                            "reason": "No department context",
                        }
                    )
                    continue

                # Clean first_name and last_name (strip whitespace if present)
                first_name = str(prenom).strip() if prenom else None
                last_name = str(nom).strip() if nom else None

                dataset.append(
                    [
                        email_clean,
                        current_department,
                        current_arrondissement,  # May be None for dept-level
                        first_name,
                        last_name,
                    ]
                )

        wb.close()

        if skipped_rows:
            logger.warning(
                f"Skipped {len(skipped_rows)} rows without valid context: {skipped_rows}"
            )

        logger.info(
            f"Parsed {len(dataset)} user records from Excel ({len(skipped_rows)} skipped)"
        )

        return dataset

    def import_action(self, request, *args, **kwargs):
        """
        Override ImportMixin's import_action to preprocess hierarchical Excel files.

        If an Excel file is uploaded (.xlsx or .xls), parse it with ExcelUserDataParser
        to convert hierarchical structure into flat tabular data before import.
        """
        if request.method == "POST" and request.FILES.get("import_file"):
            import_file = request.FILES["import_file"]

            # Check if Excel file (by extension)
            if import_file.name.endswith((".xlsx", ".xls")):
                try:
                    # Reset file pointer to beginning for openpyxl
                    import_file.seek(0)

                    # Parse Excel to flat dataset
                    dataset = self.parse_excel_to_dataset(import_file)

                    # Convert dataset to CSV and replace the uploaded file
                    csv_content = dataset.export("csv")
                    csv_bytes = csv_content.encode("utf-8")
                    csv_file = BytesIO(csv_bytes)

                    # Replace the uploaded file with preprocessed CSV
                    request.FILES["import_file"] = InMemoryUploadedFile(
                        file=csv_file,
                        field_name="import_file",
                        name="preprocessed.csv",
                        content_type="text/csv",
                        size=len(csv_bytes),
                        charset="utf-8",
                    )
                except Exception as e:
                    self.message_user(
                        request,
                        f"Erreur lors de la lecture du fichier Excel: {e}",
                        level="ERROR",
                    )

        return super().import_action(request, *args, **kwargs)


@admin.register(Adresse)
class AdresseAdmin(AllPermsForSuperUserAndViewOnlyForStaffUser, admin.ModelAdmin):
    list_display = ("label", "postal_code", "commune")
    autocomplete_fields = ("commune",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("commune")
        return queryset


@admin.register(Region)
class RegionAdmin(
    AllPermsForSuperUserAndViewOnlyForStaffUser, ImportMixin, admin.ModelAdmin
):
    resource_classes = (RegionResource,)


@admin.register(Departement)
class DepartementAdmin(
    AllPermsForSuperUserAndViewOnlyForStaffUser, ImportMixin, admin.ModelAdmin
):
    search_fields = ("name", "insee_code")
    resource_classes = (DepartementResource,)
    list_display = ("insee_code", "name", "region", "active")
    list_filter = ("region", "active")
    actions = ("activate_departement", "deactivate_departement")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and "active" in form.changed_data and obj.active:
            notify_admins(
                f"Département activé : {obj.insee_code} {obj.name}",
                f"Activé par {request.user} ({request.user.email}).",
            )

    @admin.action(description="Activer le département")
    def activate_departement(self, request, queryset):
        newly_activated = list(queryset.filter(active=False))
        queryset.update(active=True)
        if newly_activated:
            lines = "\n".join(f"- {d.insee_code} {d.name}" for d in newly_activated)
            notify_admins(
                f"Activation groupée de départements : {len(newly_activated)}",
                (
                    f"Action déclenchée par {request.user} ({request.user.email}).\n"
                    f"{lines}"
                ),
            )

    @admin.action(description="Désactiver le département")
    def deactivate_departement(self, request, queryset):
        queryset.update(active=False)


@admin.register(Arrondissement)
class ArrondissementAdmin(
    AllPermsForSuperUserAndViewOnlyForStaffUser, ImportMixin, admin.ModelAdmin
):
    search_fields = ("name", "insee_code")
    list_display = (
        "insee_code",
        "name",
        "departement__name",
        "departement__region__name",
    )
    resource_classes = (ArrondissementResource,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("departement", "departement__region")


@admin.register(Commune)
class CommuneAdmin(
    AllPermsForSuperUserAndViewOnlyForStaffUser, ImportMixin, admin.ModelAdmin
):
    resource_classes = (CommuneResource,)
    list_display = ("name", "insee_code", "departement", "arrondissement")
    list_filter = ("departement__region", "departement", "arrondissement")
    search_fields = (
        "name",
        "insee_code",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("arrondissement", "departement")
        return queryset


@admin.register(Perimetre)
class PerimetreAdmin(AllPermsForSuperUserAndViewOnlyForStaffUser, admin.ModelAdmin):
    search_fields = (
        "departement__insee_code",
        "departement__name",
        "region__name",
        "arrondissement__name",
    )
    list_display = (
        "__str__",
        "type",
        "region_id",
        "departement_id",
        "arrondissement_id",
        "user_count",
    )

    def has_add_permission(self, request):
        """Disable add permission - keep autocomplete but prevent creation."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable change permission - keep autocomplete but prevent editing."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable delete permission - keep autocomplete but prevent deletion."""
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("departement", "region")
        queryset = queryset.annotate(user_count=Count("collegue"))
        return queryset

    def user_count(self, obj):
        return obj.user_count

    user_count.admin_order_field = "user_count"
    user_count.short_description = "Nb d’utilisateurs"


@admin.register(LogEntry)
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


admin.site.unregister(Group)
