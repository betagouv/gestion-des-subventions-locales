# Generated by Django 5.1.4 on 2025-01-09 14:40

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_core", "0006_commune_arrondissement"),
        ("gsl_programmation", "0002_rename_scenario_simulation_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="enveloppe",
            name="unicity_by_perimeter_and_type",
        ),
        migrations.RemoveConstraint(
            model_name="enveloppe",
            name="only_one_perimeter",
        ),
        migrations.RemoveConstraint(
            model_name="enveloppe",
            name="dsil_regional_perimeter",
        ),
        migrations.RemoveConstraint(
            model_name="enveloppe",
            name="detr_departemental_perimeter",
        ),
        migrations.RemoveField(
            model_name="enveloppe",
            name="perimetre_arrondissement",
        ),
        migrations.RemoveField(
            model_name="enveloppe",
            name="perimetre_departement",
        ),
        migrations.RemoveField(
            model_name="enveloppe",
            name="perimetre_region",
        ),
        migrations.AddField(
            model_name="enveloppe",
            name="perimetre",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="gsl_core.perimetre",
                verbose_name="Périmètre",
            ),
        ),
        migrations.AddConstraint(
            model_name="enveloppe",
            constraint=models.UniqueConstraint(
                fields=("annee", "type", "perimetre"),
                name="unicity_by_perimeter_and_type",
            ),
        ),
    ]
