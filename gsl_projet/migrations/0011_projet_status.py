# Generated by Django 5.1.4 on 2025-02-17 10:33

import django_fsm
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0010_alter_demandeur_siret"),
    ]

    operations = [
        migrations.AddField(
            model_name="projet",
            name="status",
            field=django_fsm.FSMField(
                choices=[
                    ("accepted", "✅ Accepté"),
                    ("refused", "❌ Refusé"),
                    ("processing", "🔄 En traitement"),
                    ("unanswered", "⛔️ Classé sans suite"),
                ],
                default="processing",
                max_length=50,
                protected=True,
                verbose_name="Statut",
            ),
        ),
    ]
