# Generated by Django 5.1.1 on 2024-11-13 15:57

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="projet",
            name="arrondissement",
        ),
        migrations.RemoveField(
            model_name="projet",
            name="demandeur",
        ),
    ]