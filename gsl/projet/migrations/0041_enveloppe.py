import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def move_content_type_to_gsl_projet(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="gsl_programmation", model="enveloppe").update(
        app_label="gsl_projet"
    )


def move_content_type_back(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="gsl_projet", model="enveloppe").update(
        app_label="gsl_programmation"
    )


state_operations = [
    migrations.CreateModel(
        name="Enveloppe",
        fields=[
            (
                "id",
                models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name="ID",
                ),
            ),
            (
                "created_at",
                models.DateTimeField(
                    auto_now_add=True, verbose_name="Date de création"
                ),
            ),
            (
                "updated_at",
                models.DateTimeField(
                    auto_now=True, verbose_name="Date de modification"
                ),
            ),
            (
                "dotation",
                models.CharField(
                    choices=[("DETR", "DETR"), ("DSIL", "DSIL")],
                    verbose_name="Dotation",
                ),
            ),
            (
                "montant",
                models.DecimalField(
                    decimal_places=2,
                    max_digits=14,
                    validators=[django.core.validators.MinValueValidator(0)],
                    verbose_name="Montant",
                ),
            ),
            ("annee", models.IntegerField(verbose_name="Année")),
            (
                "deleguee_by",
                models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    to="gsl_projet.enveloppe",
                    verbose_name="Enveloppe déléguée",
                ),
            ),
            (
                "perimetre",
                models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to="gsl_core.perimetre",
                    verbose_name="Périmètre",
                ),
            ),
        ],
    ),
    migrations.AddConstraint(
        model_name="enveloppe",
        constraint=models.UniqueConstraint(
            fields=("annee", "dotation", "perimetre"),
            name="unicity_by_perimeter_and_dotation",
            violation_error_message="Cette enveloppe est déjà programmée pour ce territoire et cette dotation.",
        ),
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("gsl_core", "0018_merge_0017_commune_siren_0017_importstate"),
        ("gsl_programmation", "0030_rename_enveloppe_table"),
        ("gsl_projet", "0040_rename_dotationprojet_enveloppeprojet"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(state_operations=state_operations),
        migrations.AlterField(
            model_name="enveloppeprojet",
            name="enveloppe",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="gsl_projet.enveloppe",
                verbose_name="Enveloppe",
            ),
        ),
        # Reuse the existing row instead of letting Django create a second one:
        # 645 django_admin_log entries point at it, and an orphaned ContentType
        # detaches the whole admin history of the enveloppes.
        migrations.RunPython(
            move_content_type_to_gsl_projet, move_content_type_back, elidable=True
        ),
    ]
