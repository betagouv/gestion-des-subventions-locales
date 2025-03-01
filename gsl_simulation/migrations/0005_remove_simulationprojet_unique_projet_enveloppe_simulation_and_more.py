# Generated by Django 5.1.4 on 2025-02-26 11:40

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_programmation", "0008_alter_programmationprojet_status"),
        ("gsl_projet", "0014_merge_20250225_1159"),
        (
            "gsl_simulation",
            "0004_remove_simulationprojet_unique_projet_enveloppe_projet_and_more",
        ),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="simulationprojet",
            name="unique_projet_enveloppe_simulation",
        ),
        migrations.AddConstraint(
            model_name="simulationprojet",
            constraint=models.UniqueConstraint(
                fields=("projet", "simulation"),
                name="unique_projet_simulation",
                nulls_distinct=True,
            ),
        ),
    ]
