# Generated by Django 5.1.7 on 2025-03-21 10:50

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_simulation", "0009_alter_simulationprojet_status"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="simulation",
            options={
                "verbose_name": "Simulation",
                "verbose_name_plural": "Simulations",
            },
        ),
    ]
