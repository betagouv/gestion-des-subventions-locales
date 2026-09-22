from django.db import migrations

state_operations = [
    migrations.DeleteModel("Enveloppe"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("gsl_historique", "0010_alter_projetaction_enveloppe"),
        ("gsl_programmation", "0030_rename_enveloppe_table"),
        ("gsl_projet", "0041_enveloppe"),
        ("gsl_simulation", "0029_alter_simulation_enveloppe"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(state_operations=state_operations),
    ]
