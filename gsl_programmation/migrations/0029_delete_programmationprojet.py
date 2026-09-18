from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_programmation", "0028_remove_programmationprojet_status"),
        ("gsl_projet", "0039_fusion_programmation_projet"),
        ("gsl_notification", "0029_fusion_programmation_projet"),
    ]

    operations = [
        migrations.DeleteModel(
            name="ProgrammationProjet",
        ),
    ]
