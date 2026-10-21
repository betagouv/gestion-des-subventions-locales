from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0039_fusion_programmation_projet"),
        ("gsl_notification", "0029_fusion_programmation_projet"),
        ("gsl_programmation", "0029_delete_programmationprojet"),
        ("gsl_simulation", "0027_alter_bulkstatusjob_target_status"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="DotationProjet",
            new_name="EnveloppeProjet",
        ),
        migrations.AlterModelOptions(
            name="enveloppeprojet",
            options={
                "verbose_name": "Enveloppe projet",
                "verbose_name_plural": "Enveloppes projet",
            },
        ),
    ]
