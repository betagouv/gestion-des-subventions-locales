# Generated by Django 5.1.1 on 2024-11-26 15:59

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_core", "0004_alter_adresse_commune_alter_adresse_postal_code_and_more"),
        (
            "gsl_demarches_simplifiees",
            "0003_alter_dossier_demande_autres_aides_and_more",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="FormeJuridique",
            fields=[
                (
                    "code",
                    models.CharField(
                        primary_key=True, serialize=False, verbose_name="Code"
                    ),
                ),
                ("libelle", models.CharField(verbose_name="Libellé")),
            ],
            options={
                "verbose_name": "Forme Juridique",
                "verbose_name_plural": "Formes Juridiques",
            },
        ),
        migrations.CreateModel(
            name="Naf",
            fields=[
                (
                    "code",
                    models.CharField(
                        primary_key=True, serialize=False, verbose_name="Code"
                    ),
                ),
                ("libelle", models.CharField(verbose_name="Libellé")),
            ],
            options={
                "verbose_name": "Code NAF",
                "verbose_name_plural": "Codes NAF",
            },
        ),
        migrations.CreateModel(
            name="PersonneMorale",
            fields=[
                (
                    "siret",
                    models.CharField(
                        primary_key=True,
                        serialize=False,
                        unique=True,
                        verbose_name="SIRET",
                    ),
                ),
                (
                    "raison_sociale",
                    models.CharField(blank=True, verbose_name="Raison Sociale"),
                ),
                ("siren", models.CharField(blank=True, verbose_name="SIREN")),
                (
                    "address",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_core.adresse",
                        verbose_name="Adresse",
                    ),
                ),
                (
                    "forme_juridique",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_demarches_simplifiees.formejuridique",
                    ),
                ),
                (
                    "naf",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_demarches_simplifiees.naf",
                    ),
                ),
            ],
            options={
                "verbose_name": "Personne morale",
                "verbose_name_plural": "Personnes morales",
            },
        ),
        migrations.AddField(
            model_name="dossier",
            name="ds_demandeur",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="gsl_demarches_simplifiees.personnemorale",
                verbose_name="Demandeur",
            ),
        ),
    ]
