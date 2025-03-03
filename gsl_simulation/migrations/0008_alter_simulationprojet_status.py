# Generated by Django 5.1.4 on 2025-03-03 16:27

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_simulation", "0007_alter_simulationprojet_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="simulationprojet",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "🔄 En traitement"),
                    ("valid", "✅ Accepté"),
                    ("provisoire", "✔️ Accepté provisoirement"),
                    ("cancelled", "❌ Refusé"),
                    ("unanswered", "⛔️ Classé sans suite"),
                ],
                default="draft",
                verbose_name="État",
            ),
        ),
    ]
