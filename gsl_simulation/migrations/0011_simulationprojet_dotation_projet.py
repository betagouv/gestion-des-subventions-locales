# Generated by Django 5.1.7 on 2025-04-02 08:02

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0018_dotationprojet"),
        ("gsl_simulation", "0010_alter_simulation_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="simulationprojet",
            name="dotation_projet",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="gsl_projet.dotationprojet",
            ),
        ),
    ]
