import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0040_rename_dotationprojet_enveloppeprojet"),
        ("gsl_simulation", "0027_alter_bulkstatusjob_target_status"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="simulationprojet",
            name="unique_projet_simulation",
        ),
        migrations.RenameField(
            model_name="simulationprojet",
            old_name="dotation_projet",
            new_name="enveloppe_projet",
        ),
        migrations.AlterField(
            model_name="simulationprojet",
            name="enveloppe_projet",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="gsl_projet.enveloppeprojet",
            ),
        ),
        migrations.AddConstraint(
            model_name="simulationprojet",
            constraint=models.UniqueConstraint(
                fields=("enveloppe_projet", "simulation"),
                name="unique_projet_simulation",
                nulls_distinct=True,
            ),
        ),
    ]
