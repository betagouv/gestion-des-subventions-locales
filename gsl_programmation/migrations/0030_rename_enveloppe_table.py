from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_programmation", "0029_delete_programmationprojet"),
    ]

    operations = [
        migrations.AlterModelTable("Enveloppe", "gsl_projet_enveloppe"),
    ]
