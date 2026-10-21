from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_ds_proxy", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="proxytoken",
            name="instructeurs",
        ),
        migrations.AddField(
            model_name="proxytoken",
            name="groupe_instructeur_ds_id",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=255,
                verbose_name="ID du groupe instructeur DS",
            ),
        ),
    ]
