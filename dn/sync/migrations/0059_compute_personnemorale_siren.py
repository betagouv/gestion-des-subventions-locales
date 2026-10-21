from django.db import migrations, models
from django.db.models.functions import Substr


def compute_siren_from_siret(apps, schema_editor):
    PersonneMorale = apps.get_model("gsl_demarches_simplifiees", "PersonneMorale")
    PersonneMorale.objects.update(siren=Substr("siret", 1, 9))


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_demarches_simplifiees", "0058_demarche_deleted_cursor_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="personnemorale",
            name="siren",
            field=models.CharField(
                blank=True,
                help_text="Calculé automatiquement à partir du SIRET.",
                verbose_name="SIREN",
            ),
        ),
        migrations.RunPython(compute_siren_from_siret, migrations.RunPython.noop),
    ]
