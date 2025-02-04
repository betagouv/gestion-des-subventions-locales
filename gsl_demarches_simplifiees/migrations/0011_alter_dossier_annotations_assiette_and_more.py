# Generated by Django 5.1.4 on 2025-02-04 09:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_demarches_simplifiees", "0010_alter_dossier_projet_adresse"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dossier",
            name="annotations_assiette",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="Montant des dépenses éligibles retenues (€)",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="annotations_montant_accorde",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="Montant définitif de la subvention (€)",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="annotations_taux",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="Taux de subvention (%)",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="date_achevement",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="Date prévisionnelle d'achèvement de l'opération",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="demande_montant",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="Montant de l'aide demandée",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="environnement_objectifs",
            field=models.ManyToManyField(
                blank=True,
                to="gsl_demarches_simplifiees.objectifenvironnemental",
                verbose_name="Si oui, indiquer quels sont les objectifs environnementaux impactés favorablement.",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="finance_cout_total",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="Coût total de l'opération (en euros HT)",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="projet_contractualisation",
            field=models.ManyToManyField(
                blank=True,
                to="gsl_demarches_simplifiees.projetcontractualisation",
                verbose_name="Contractualisation : le projet est-il inscrit dans un ou plusieurs contrats avec l'Etat ?",
            ),
        ),
        migrations.AlterField(
            model_name="dossier",
            name="projet_zonage",
            field=models.ManyToManyField(
                blank=True,
                to="gsl_demarches_simplifiees.projetzonage",
                verbose_name="Zonage spécifique : le projet est il situé dans l'une des zones suivantes ?",
            ),
        ),
    ]
