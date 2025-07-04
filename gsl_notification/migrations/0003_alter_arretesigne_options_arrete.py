# Generated by Django 5.2.2 on 2025-06-19 15:11

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_notification", "0002_rename_uploaded_at_arretesigne_created_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="arretesigne",
            options={
                "verbose_name": "Arrêté signé",
                "verbose_name_plural": "Arrêtés signés",
            },
        ),
        migrations.CreateModel(
            name="Arrete",
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
                    "content",
                    models.JSONField(
                        blank=True,
                        help_text="Contenu JSON de l'arrêté, utilisé pour les exports.",
                        null=True,
                        verbose_name="Contenu de l'arrêté",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "programmation_projet",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="arrete",
                        to="gsl_programmation.programmationprojet",
                        verbose_name="Programmation projet",
                    ),
                ),
            ],
            options={
                "verbose_name": "Arrêté",
                "verbose_name_plural": "Arrêtés",
            },
        ),
    ]
