import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Exists, OuterRef, Subquery


def copy_from_programmation_projet(apps, schema_editor):
    DotationProjet = apps.get_model("gsl_projet", "DotationProjet")
    ProgrammationProjet = apps.get_model("gsl_programmation", "ProgrammationProjet")

    programmation = ProgrammationProjet.objects.filter(dotation_projet=OuterRef("pk"))
    DotationProjet.objects.filter(Exists(programmation)).update(
        enveloppe_id=Subquery(programmation.values("enveloppe_id")[:1]),
        montant=Subquery(programmation.values("montant")[:1]),
        date_programmation=Subquery(programmation.values("created_at")[:1]),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_programmation", "0028_remove_programmationprojet_status"),
        (
            "gsl_projet",
            "0038_remove_dotationprojet_detr_categories_delete_categoriedetr",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="dotationprojet",
            name="date_programmation",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Date de programmation"
            ),
        ),
        migrations.AddField(
            model_name="dotationprojet",
            name="enveloppe",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="gsl_programmation.enveloppe",
                verbose_name="Enveloppe",
            ),
        ),
        migrations.AddField(
            model_name="dotationprojet",
            name="montant",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                verbose_name="Montant",
            ),
        ),
        migrations.RunPython(
            copy_from_programmation_projet, migrations.RunPython.noop, elidable=True
        ),
        migrations.AddConstraint(
            model_name="dotationprojet",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("enveloppe__isnull", True), ("status", "processing")),
                    models.Q(
                        models.Q(("status", "processing"), _negated=True),
                        ("enveloppe__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="enveloppe_ssi_dotation_traitee",
                violation_error_message="Une dotation en traitement ne peut pas porter d'enveloppe, et une dotation traitée doit en porter une.",
            ),
        ),
    ]
