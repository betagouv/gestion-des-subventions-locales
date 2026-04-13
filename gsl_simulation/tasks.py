from celery import shared_task
from django.db.models import F

from gsl_simulation.models import SimulationProjet


@shared_task
def task_clean_simulation_projets_with_outdated_programmation():
    SimulationProjet.objects.filter(
        dotation_projet__programmation_projet__enveloppe__annee__lt=F(
            "simulation__enveloppe__annee"
        )
    ).delete()
