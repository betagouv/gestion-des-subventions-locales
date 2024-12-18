# Generated by Django 5.1.1 on 2024-12-12 16:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0005_projet_assiette"),
    ]

    operations = [
        migrations.AddField(
            model_name="projet",
            name="avis_commission_detr",
            field=models.BooleanField(
                help_text="Pour les projets de plus de 100 000 €",
                null=True,
                verbose_name="Avis commission DETR",
            ),
        ),
        migrations.AddField(
            model_name="projet",
            name="free_comment",
            field=models.TextField(
                blank=True, default="", verbose_name="Commentaires libres"
            ),
        ),
    ]