from django.db import migrations, models


def translate_programmation_projet_ids(apps, schema_editor):
    ExportJob = apps.get_model("gsl_notification", "ExportJob")
    ProgrammationProjet = apps.get_model("gsl_programmation", "ProgrammationProjet")

    dotation_projet_id_by_pk = dict(
        ProgrammationProjet.objects.values_list("pk", "dotation_projet_id")
    )
    for job in ExportJob.objects.exclude(pp_ids=[]).iterator():
        job.dotation_projet_ids = [
            dotation_projet_id_by_pk[pk]
            for pk in job.pp_ids
            if pk in dotation_projet_id_by_pk
        ]
        job.save(update_fields=["dotation_projet_ids"])


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_notification", "0028_documents_point_to_dotation_projet"),
        ("gsl_programmation", "0028_remove_programmationprojet_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="exportjob",
            name="dotation_projet_ids",
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(
            translate_programmation_projet_ids,
            migrations.RunPython.noop,
            elidable=True,
        ),
        migrations.RemoveField(
            model_name="exportjob",
            name="pp_ids",
        ),
    ]
