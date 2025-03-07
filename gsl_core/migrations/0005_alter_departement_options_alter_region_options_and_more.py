# Generated by Django 5.1.4 on 2024-12-18 09:32

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_core", "0004_alter_adresse_commune_alter_adresse_postal_code_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="departement",
            options={"ordering": ["insee_code"], "verbose_name": "Département"},
        ),
        migrations.AlterModelOptions(
            name="region",
            options={"ordering": ["name"], "verbose_name": "Région"},
        ),
        migrations.CreateModel(
            name="Perimetre",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "arrondissement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_core.arrondissement",
                        verbose_name="Arrondissement",
                    ),
                ),
                (
                    "departement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_core.departement",
                        verbose_name="Département",
                    ),
                ),
                (
                    "region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_core.region",
                        verbose_name="Région",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="collegue",
            name="perimetre",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="gsl_core.perimetre",
            ),
        ),
        migrations.AddConstraint(
            model_name="perimetre",
            constraint=models.UniqueConstraint(
                fields=("region", "departement", "arrondissement"),
                name="unicity_by_perimeter",
                nulls_distinct=False,
            ),
        ),
    ]
