# Generated by Django 5.1.7 on 2025-04-02 13:51

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0018_dotationprojet"),
        ("gsl_simulation", "0011_simulationprojet_dotation_projet"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="simulationprojet",
            name="unique_projet_simulation",
        ),
        migrations.AddConstraint(
            model_name="simulationprojet",
            constraint=models.UniqueConstraint(
                fields=("dotation_projet", "simulation"),
                name="unique_projet_simulation",
                nulls_distinct=True,
            ),
        ),
    ]
