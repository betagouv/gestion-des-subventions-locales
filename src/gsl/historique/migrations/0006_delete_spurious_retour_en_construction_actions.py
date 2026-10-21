from django.db import migrations


def delete_spurious_retour_en_construction_actions(apps, schema_editor):
    """
    Un bug (corrigé entre-temps) créait un événement "retour en construction"
    dès que la date de passage en construction d'un dossier changeait, même
    pour des dossiers n'étant jamais passés en instruction. On ne garde que
    les événements dont le dossier montre un vrai retour : une date de
    passage en construction plus récente que sa date de passage en
    instruction.
    """
    ProjetAction = apps.get_model("gsl_historique", "ProjetAction")

    for action in ProjetAction.objects.filter(
        action_type="retour_en_construction"
    ).select_related("projet__dossier_ds"):
        dossier = action.projet.dossier_ds
        instruction_date = dossier.ds_date_passage_en_instruction
        construction_date = dossier.ds_date_passage_en_construction

        is_real_retour = (
            instruction_date
            and construction_date
            and construction_date > instruction_date
        )
        if not is_real_retour:
            action.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_historique", "0005_projetaction_notification_document_and_more"),
    ]

    operations = [
        migrations.RunPython(
            delete_spurious_retour_en_construction_actions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
