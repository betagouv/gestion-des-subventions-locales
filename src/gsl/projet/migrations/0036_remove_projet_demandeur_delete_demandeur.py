from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0035_alter_dotationprojet_assiette"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="projet",
            name="demandeur",
        ),
        migrations.DeleteModel(
            name="Demandeur",
        ),
    ]
