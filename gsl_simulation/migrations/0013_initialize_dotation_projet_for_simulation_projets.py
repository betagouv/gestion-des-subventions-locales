# Generated by Django 5.1.7 on 2025-04-02 14:25

from django.db import migrations


def set_dotation_projet_for_simulation_projets(apps, schema_editor):
    SimulationProjet = apps.get_model("gsl_simulation", "SimulationProjet")
    DotationProjet = apps.get_model("gsl_projet", "DotationProjet")
    for simulation_projet in SimulationProjet.objects.all():
        try:
            simulation_projet.dotation_projet = DotationProjet.objects.get(
                projet=simulation_projet.projet,
                dotation=simulation_projet.simulation.enveloppe.dotation,
            )
            simulation_projet.save()
        except AttributeError as e:
            print(
                f"Could not find enveloppe dotation for simulation projet {simulation_projet.pk}",
                e,
            )
        except DotationProjet.DoesNotExist as e:
            print(
                f"Could not find dotation projet for simulation projet {simulation_projet.pk}",
                e,
            )


class Migration(migrations.Migration):
    dependencies = [
        (
            "gsl_simulation",
            "0012_remove_simulationprojet_unique_projet_simulation_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            set_dotation_projet_for_simulation_projets,
            reverse_code=migrations.RunPython.noop,
        )
    ]
