# Generated by Django 5.1.4 on 2025-02-11 16:48

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_simulation", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="simulationprojet",
            name="unique_valid_simulation_per_project",
        ),
    ]
