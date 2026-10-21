import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_notification", "0029_fusion_programmation_projet"),
        ("gsl_projet", "0040_rename_dotationprojet_enveloppeprojet"),
    ]

    operations = [
        migrations.RenameField(
            model_name="annexe",
            old_name="dotation_projet",
            new_name="enveloppe_projet",
        ),
        migrations.RenameField(
            model_name="arrete",
            old_name="dotation_projet",
            new_name="enveloppe_projet",
        ),
        migrations.RenameField(
            model_name="lettreetarretesignes",
            old_name="dotation_projet",
            new_name="enveloppe_projet",
        ),
        migrations.RenameField(
            model_name="lettrenotification",
            old_name="dotation_projet",
            new_name="enveloppe_projet",
        ),
        migrations.RenameField(
            model_name="lettrerefus",
            old_name="dotation_projet",
            new_name="enveloppe_projet",
        ),
        migrations.RenameField(
            model_name="lettrerefussignee",
            old_name="dotation_projet",
            new_name="enveloppe_projet",
        ),
        migrations.RenameField(
            model_name="exportjob",
            old_name="dotation_projet_ids",
            new_name="enveloppe_projet_ids",
        ),
        migrations.AlterField(
            model_name="annexe",
            name="enveloppe_projet",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="annexes",
                to="gsl_projet.enveloppeprojet",
            ),
        ),
        migrations.AlterField(
            model_name="lettreetarretesignes",
            name="enveloppe_projet",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lettre_et_arrete_signes",
                to="gsl_projet.enveloppeprojet",
            ),
        ),
        migrations.AlterField(
            model_name="lettrerefussignee",
            name="enveloppe_projet",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lettre_refus_signee",
                to="gsl_projet.enveloppeprojet",
            ),
        ),
        migrations.AlterField(
            model_name="arrete",
            name="enveloppe_projet",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="%(class)s",
                to="gsl_projet.enveloppeprojet",
                verbose_name="Enveloppe projet",
            ),
        ),
        migrations.AlterField(
            model_name="lettrenotification",
            name="enveloppe_projet",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="%(class)s",
                to="gsl_projet.enveloppeprojet",
                verbose_name="Enveloppe projet",
            ),
        ),
        migrations.AlterField(
            model_name="lettrerefus",
            name="enveloppe_projet",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="%(class)s",
                to="gsl_projet.enveloppeprojet",
                verbose_name="Enveloppe projet",
            ),
        ),
    ]
