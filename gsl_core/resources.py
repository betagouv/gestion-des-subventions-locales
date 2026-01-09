from import_export import resources
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from .models import Arrondissement, Collegue, Commune, Departement, Perimetre, Region


class RegionResource(resources.ModelResource):
    """
    Documentation for the imported CSV files is available at
    https://www.insee.fr/fr/information/7766585
    """

    insee_code = Field(attribute="insee_code", column_name="REG")
    name = Field(attribute="name", column_name="NCCENR")

    class Meta:
        model = Region
        import_id_fields = ("insee_code",)


class DepartementResource(resources.ModelResource):
    insee_code = Field(attribute="insee_code", column_name="DEP")
    name = Field(attribute="name", column_name="NCCENR")
    region = Field(
        attribute="region",
        column_name="REG",
        widget=ForeignKeyWidget(Region, field="insee_code"),
    )

    class Meta:
        model = Departement
        import_id_fields = ("insee_code",)


class ArrondissementResource(resources.ModelResource):
    insee_code = Field(attribute="insee_code", column_name="ARR")
    name = Field(attribute="name", column_name="NCCENR")
    departement = Field(
        attribute="departement",
        column_name="DEP",
        widget=ForeignKeyWidget(Departement, field="insee_code"),
    )

    class Meta:
        model = Arrondissement
        import_id_fields = ("insee_code",)


class CommuneResource(resources.ModelResource):
    insee_code = Field(attribute="insee_code", column_name="COM")
    name = Field(attribute="name", column_name="NCCENR")
    departement = Field(
        attribute="departement",
        column_name="DEP",
        widget=ForeignKeyWidget(Departement, field="insee_code"),
    )
    arrondissement = Field(
        attribute="arrondissement",
        column_name="ARR",
        widget=ForeignKeyWidget(Arrondissement, field="insee_code"),
    )

    def skip_row(self, instance, original, row, import_validation_errors=None):
        if row["TYPECOM"] != "COM":
            # avoid communes déléguées and communes associées
            return True
        if not row["ARR"]:
            return True
        return super().skip_row(instance, original, row, import_validation_errors)

    class Meta:
        model = Commune
        import_id_fields = ("insee_code",)
        use_bulk = True
        skip_unchanged = True


class CollegueResource(resources.ModelResource):
    """
    Resource for importing users (Collegue) with automatic perimetre assignment
    based on department and arrondissement codes.

    Expected input columns:
    - email: User email address (used for upsert)
    - departement_code: Department INSEE code (e.g., '01', '2A')
    - arrondissement_code: Arrondissement INSEE code (e.g., '011') or None for dept-level

    The resource will:
    - Create or update users by email
    - Set username = email
    - Create/find the appropriate Perimetre
    - Set unusable password for new users (ProConnect OIDC authentication)
    - Set is_active=True, is_staff=False by default
    """

    email = Field(attribute="email", column_name="email")
    departement_code = Field(column_name="departement_code")
    arrondissement_code = Field(column_name="arrondissement_code")

    class Meta:
        model = Collegue
        import_id_fields = ("email",)  # Upsert by email
        fields = (
            "email",
            "username",
            "perimetre",
            "is_active",
            "is_staff",
            "departement_code",
            "arrondissement_code",
        )
        skip_unchanged = True

    def before_import_row(self, row, **kwargs):
        """
        Transform row data before import:
        - Set username = email
        - Lookup/create Perimetre from geographic codes
        - Set default user flags
        - Track if this will be a new user
        """
        # Set username = email
        row["username"] = row["email"]

        # Check if user already exists (for password handling later)
        email = row.get("email")
        row["_is_new_user"] = not Collegue.objects.filter(email=email).exists()

        # Lookup/create Perimetre (similar to EnveloppeResource pattern)
        dept_code = row.get("departement_code")
        arr_code = row.get("arrondissement_code")

        if arr_code:
            # Arrondissement-level perimeter
            # Example: email='user@ain.gouv.fr', arr_code='011'
            # Creates: Perimetre(region=84, departement='01', arrondissement='011')
            arr = Arrondissement.objects.get(insee_code=arr_code)
            perimetre, _ = Perimetre.objects.get_or_create(
                region=arr.departement.region,
                departement=arr.departement,
                arrondissement=arr,
            )
        elif dept_code:
            # Department-level perimeter
            # Example: email='pref@ain.gouv.fr', dept_code='01', arr_code=None
            # Creates: Perimetre(region=84, departement='01', arrondissement=None)
            dept = Departement.objects.get(insee_code=dept_code)
            perimetre, _ = Perimetre.objects.get_or_create(
                region=dept.region,
                departement=dept,
                arrondissement=None,  # Explicitly None for dept-level
            )
        else:
            raise ValueError("Missing departement_code in row data")

        # Store perimetre ID for import
        row["perimetre"] = perimetre.id

        # Set default user flags
        row["is_active"] = True
        row["is_staff"] = False

    def after_save_instance(
        self, instance, row, using_transactions=None, dry_run=False, **kwargs
    ):
        """
        Post-processing after instance is saved.
        Set unusable password for new users (they authenticate via ProConnect OIDC).
        """
        if not dry_run:
            is_new = row.get("_is_new_user", False)
            if is_new:
                instance.set_unusable_password()
                instance.save(update_fields=["password"])
