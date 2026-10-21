from django.db import migrations

DOTATION_DETR = "DETR"
DOTATION_DSIL = "DSIL"


def backfill_assiette(apps, schema_editor):
    DotationProjet = apps.get_model("gsl_projet", "DotationProjet")

    for dp in DotationProjet.objects.filter(assiette__isnull=True).select_related(
        "projet__dossier_ds"
    ):
        dossier = dp.projet.dossier_ds

        if dp.dotation == DOTATION_DETR:
            assiette = dossier.annotations_assiette_detr
        elif dp.dotation == DOTATION_DSIL:
            assiette = dossier.annotations_assiette_dsil
        else:
            assiette = None

        if assiette is None:
            assiette = dossier.finance_cout_total

        if assiette is not None:
            dp.assiette = assiette
            dp.save(update_fields=["assiette"])


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_projet", "0036_remove_projet_demandeur_delete_demandeur"),
    ]

    operations = [
        migrations.RunPython(backfill_assiette, migrations.RunPython.noop),
    ]
