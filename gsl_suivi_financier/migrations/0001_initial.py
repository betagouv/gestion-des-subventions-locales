import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("gsl_core", "0016_alter_departement_active"),
    ]

    operations = [
        migrations.CreateModel(
            name="Beneficiaire",
            fields=[
                (
                    "siren",
                    models.CharField(
                        max_length=9,
                        primary_key=True,
                        serialize=False,
                        verbose_name="SIREN",
                    ),
                ),
                ("nom", models.CharField(max_length=200, verbose_name="Nom")),
                ("type", models.CharField(max_length=50, verbose_name="Type")),
            ],
            options={
                "verbose_name": "Bénéficiaire",
                "verbose_name_plural": "Bénéficiaires",
                "ordering": ["nom"],
            },
        ),
        migrations.CreateModel(
            name="SubventionDgcl",
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
                (
                    "exercice",
                    models.PositiveSmallIntegerField(verbose_name="Exercice"),
                ),
                (
                    "dispositif",
                    models.CharField(max_length=80, verbose_name="Dispositif"),
                ),
                (
                    "programme",
                    models.PositiveSmallIntegerField(verbose_name="Programme"),
                ),
                (
                    "intitule",
                    models.TextField(verbose_name="Intitulé du projet"),
                ),
                (
                    "cout_ht",
                    models.DecimalField(
                        decimal_places=2, max_digits=14, verbose_name="Coût HT"
                    ),
                ),
                (
                    "subvention",
                    models.DecimalField(
                        decimal_places=2, max_digits=14, verbose_name="Subvention"
                    ),
                ),
                (
                    "beneficiaire",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="gsl_suivi_financier.beneficiaire",
                        verbose_name="Bénéficiaire",
                    ),
                ),
                (
                    "commune",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_core.commune",
                        verbose_name="Commune",
                    ),
                ),
                (
                    "departement",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="gsl_core.departement",
                        verbose_name="Département",
                    ),
                ),
            ],
            options={
                "verbose_name": "Subvention DGCL",
                "verbose_name_plural": "Subventions DGCL",
                "ordering": ["-exercice"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="subventiondgcl",
            unique_together={("exercice", "dispositif", "beneficiaire", "intitule")},
        ),
    ]
