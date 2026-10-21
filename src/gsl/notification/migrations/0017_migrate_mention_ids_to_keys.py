from bs4 import BeautifulSoup
from django.db import migrations

ID_TO_KEY = {
    "1": "nom-beneficiaire",
    "2": "projet-intitule",
    "3": "nom-departement",
    "4": "montant-subvention",
    "5": "taux-subvention",
    "6": "date-commencement",
    "7": "date-achevement",
}

KEY_TO_ID = {v: k for k, v in ID_TO_KEY.items()}


def migrate_content(content, mapping):
    if not content:
        return content
    soup = BeautifulSoup(content, "html.parser")
    changed = False
    for span in soup.find_all("span", class_="mention"):
        old_id = span.get("data-id")
        if old_id in mapping:
            span["data-id"] = mapping[old_id]
            changed = True
    return str(soup) if changed else content


def migrate_ids_to_keys(apps, schema_editor):
    for model_name in ("ModeleArrete", "ModeleLettreNotification"):
        Model = apps.get_model("gsl_notification", model_name)
        for instance in Model.objects.exclude(content=""):
            new_content = migrate_content(instance.content, ID_TO_KEY)
            if new_content != instance.content:
                Model.objects.filter(pk=instance.pk).update(content=new_content)


def migrate_keys_to_ids(apps, schema_editor):
    for model_name in ("ModeleArrete", "ModeleLettreNotification"):
        Model = apps.get_model("gsl_notification", model_name)
        for instance in Model.objects.exclude(content=""):
            new_content = migrate_content(instance.content, KEY_TO_ID)
            if new_content != instance.content:
                Model.objects.filter(pk=instance.pk).update(content=new_content)


class Migration(migrations.Migration):
    dependencies = [
        (
            "gsl_notification",
            "0016_modelearrete_is_infected_modelearrete_last_scan_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(migrate_ids_to_keys, reverse_code=migrate_keys_to_ids),
    ]
