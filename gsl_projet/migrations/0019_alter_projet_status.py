# Generated by Django 5.1.7 on 2025-04-16 09:50

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0018_dotationprojet"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projet",
            name="status",
            field=models.CharField(
                choices=[
                    ("accepted", "✅ Accepté"),
                    ("refused", "❌ Refusé"),
                    ("processing", "🔄 En traitement"),
                    ("dismissed", "⛔️ Classé sans suite"),
                ],
                default="processing",
                verbose_name="Statut",
            ),
        ),
    ]
