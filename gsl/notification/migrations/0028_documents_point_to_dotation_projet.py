import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery

DOCUMENT_MODELS = (
    ("arrete", "%(class)s", True),
    ("lettrenotification", "%(class)s", True),
    ("lettrerefus", "%(class)s", True),
    ("lettreetarretesignes", "lettre_et_arrete_signes", True),
    ("lettrerefussignee", "lettre_refus_signee", True),
    ("annexe", "annexes", False),
)

GENERATED_DOCUMENT_MODELS = ("arrete", "lettrenotification", "lettrerefus")


def forwards(apps, schema_editor):
    programmation_projet = apps.get_model("gsl_programmation", "ProgrammationProjet")
    for model_name, _, _ in DOCUMENT_MODELS:
        apps.get_model("gsl_notification", model_name).objects.update(
            dotation_projet_id=Subquery(
                programmation_projet.objects.filter(
                    pk=OuterRef("programmation_projet_id")
                ).values("dotation_projet_id")[:1]
            )
        )


def backwards(apps, schema_editor):
    programmation_projet = apps.get_model("gsl_programmation", "ProgrammationProjet")
    for model_name, _, _ in DOCUMENT_MODELS:
        apps.get_model("gsl_notification", model_name).objects.update(
            programmation_projet_id=Subquery(
                programmation_projet.objects.filter(
                    dotation_projet_id=OuterRef("dotation_projet_id")
                ).values("pk")[:1]
            )
        )


def field(model_name, related_name, is_one_to_one, **extra):
    field_class = models.OneToOneField if is_one_to_one else models.ForeignKey
    if model_name in GENERATED_DOCUMENT_MODELS:
        extra["verbose_name"] = "Dotation projet"
    return field_class(
        on_delete=django.db.models.deletion.CASCADE,
        related_name=related_name,
        to="gsl_projet.dotationprojet",
        **extra,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_notification", "0027_merge_20260826_0918"),
        ("gsl_programmation", "0027_remove_programmationprojet_justification"),
        ("gsl_projet", "0018_dotationprojet"),
    ]

    operations = []

    for model_name, related_name, is_one_to_one in DOCUMENT_MODELS:
        operations.append(
            migrations.AddField(
                model_name=model_name,
                name="dotation_projet",
                field=field(model_name, related_name, is_one_to_one, null=True),
            )
        )

    operations.append(migrations.RunPython(forwards, backwards))

    for model_name, related_name, is_one_to_one in DOCUMENT_MODELS:
        operations.append(
            migrations.AlterField(
                model_name=model_name,
                name="dotation_projet",
                field=field(model_name, related_name, is_one_to_one),
            )
        )
        operations.append(
            migrations.RemoveField(model_name=model_name, name="programmation_projet")
        )
