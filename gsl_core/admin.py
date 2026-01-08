import logging
from io import BytesIO

import openpyxl
import tablib
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Count
from import_export.admin import ImportMixin
from import_export.formats.base_formats import CSV
from import_export.forms import ImportForm

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


@admin.register(Collegue)
class CollegueAdmin(AllPermsForStaffUser, ImportMixin, UserAdmin, admin.ModelAdmin):
    resource_classes = (CollegueResource,)
    import_template_name = "admin/gsl_core/collegue/import.html"

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "perimetre",
        "last_login",
        "ds_profile",
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
        ("Informations personnelles", {"fields": ("first_name", "last_name", "email")}),
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
    actions = ("associate_ds_profile_to_users",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("perimetre__departement", "perimetre__region")

    @admin.action(description="Association des profils DN aux utilisateurs")
    def associate_ds_profile_to_users(self, request, queryset):
        user_ids = list(queryset.values_list("id", flat=True))
        associate_or_update_ds_profile_to_users(user_ids)

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
            - Department section: (dept_code, dept_name, None, None, email)
            - Department emails: (None, None, None, None, email) - inherits department
            - Arrondissement section: (None, None, perimeter_name, arr_code, email)
            - Arrondissement emails: (None, None, None, None, email) - inherits arrondissement

        Returns:
            tablib.Dataset with columns: email, departement_code, arrondissement_code
        """
        wb = openpyxl.load_workbook(import_file, read_only=True)
        ws = wb.active

        dataset = tablib.Dataset()
        dataset.headers = ["email", "departement_code", "arrondissement_code"]

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

                dataset.append(
                    [
                        email_clean,
                        current_department,
                        current_arrondissement,  # May be None for dept-level
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
class AdresseAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    list_display = ("label", "postal_code", "commune")
    autocomplete_fields = ("commune",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("commune")
        return queryset


@admin.register(Region)
class RegionAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    resource_classes = (RegionResource,)


@admin.register(Departement)
class DepartementAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    search_fields = ("name", "insee_code")
    resource_classes = (DepartementResource,)


@admin.register(Arrondissement)
class ArrondissementAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
    search_fields = ("name", "insee_code")
    resource_classes = (ArrondissementResource,)


@admin.register(Commune)
class CommuneAdmin(AllPermsForStaffUser, ImportMixin, admin.ModelAdmin):
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
class PerimetreAdmin(AllPermsForStaffUser, admin.ModelAdmin):
    search_fields = (
        "departement__insee_code",
        "arrondissement__insee_code",
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

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.select_related("departement", "region")
        queryset = queryset.annotate(user_count=Count("collegue"))
        return queryset

    def user_count(self, obj):
        return obj.user_count

    user_count.admin_order_field = "user_count"
    user_count.short_description = "Nb d’utilisateurs"


admin.site.unregister(Group)
