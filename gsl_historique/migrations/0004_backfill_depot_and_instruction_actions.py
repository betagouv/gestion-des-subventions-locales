from django.db import migrations


def backfill_depot_and_instruction_actions(apps, schema_editor):
    Projet = apps.get_model("gsl_projet", "Projet")
    ProjetAction = apps.get_model("gsl_historique", "ProjetAction")

    for projet in Projet.objects.select_related("dossier_ds").iterator():
        dossier = projet.dossier_ds
        if dossier is None:
            continue

        if (
            dossier.ds_date_depot
            and not ProjetAction.objects.filter(
                projet=projet, action_type="depot_dossier"
            ).exists()
        ):
            ProjetAction.objects.create(
                projet=projet,
                action_type="depot_dossier",
                source="dn",
                created_at=dossier.ds_date_depot,
            )

        if (
            dossier.ds_date_passage_en_instruction
            and not ProjetAction.objects.filter(
                projet=projet, action_type="passage_en_instruction"
            ).exists()
        ):
            ProjetAction.objects.create(
                projet=projet,
                action_type="passage_en_instruction",
                source="dn",
                created_at=dossier.ds_date_passage_en_instruction,
            )


def reverse_backfill(apps, schema_editor):
    ProjetAction = apps.get_model("gsl_historique", "ProjetAction")
    ProjetAction.objects.filter(
        action_type__in=["depot_dossier", "passage_en_instruction"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_historique", "0003_projetaction_created_at_and_deactivation_reason"),
        ("gsl_projet", "0036_remove_projet_demandeur_delete_demandeur"),
    ]

    operations = [
        migrations.RunPython(
            backfill_depot_and_instruction_actions,
            reverse_code=reverse_backfill,
        ),
    ]
