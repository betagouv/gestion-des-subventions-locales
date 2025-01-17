# Generated by Django 5.1.1 on 2024-11-14 14:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_demarches_simplifiees", "0002_alter_dossier_projet_adresse"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dossier",
            name="demande_autres_aides",
            field=models.ManyToManyField(
                blank=True,
                to="gsl_demarches_simplifiees.autreaide",
                verbose_name="En 2024, comptez-vous solliciter d'autres aides publiques pour financer cette opération  ?",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="demande_eligibilite_detr",
            field=models.ManyToManyField(
                blank=True,
                to="gsl_demarches_simplifiees.critereeligibilitedetr",
                verbose_name="Eligibilité de l'opération à la DETR",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="demande_eligibilite_dsil",
            field=models.ManyToManyField(
                blank=True,
                to="gsl_demarches_simplifiees.critereeligibilitedsil",
                verbose_name="Eligibilité de l'opération à la DSIL",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="demande_priorite_dsil_detr",
            field=models.IntegerField(
                blank=True,
                null=True,
                verbose_name="Si oui, précisez le niveau de priorité de ce dossier.",
            ),
        ),
    ]
