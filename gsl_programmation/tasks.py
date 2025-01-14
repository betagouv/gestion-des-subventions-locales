from celery import shared_task

from gsl_programmation.models import Simulation, SimulationProjet
from gsl_projet.models import Projet


@shared_task
def add_enveloppe_projets_to_simulation(simulation_id):
    simulation = Simulation.objects.get(id=simulation_id)
    simulation_perimetre = simulation.enveloppe.perimetre
    # todo later: "simulation par arrondissement"
    for projet in Projet.objects.for_perimetre(simulation_perimetre).all():
        # if any SimulationProjet exists for this projet with a "definitive" status,
        # on this enveloppe, do not create a new SimulationProjet here:
        if SimulationProjet.objects.filter(
            projet=projet,
            enveloppe=simulation.enveloppe,
            status__in=(
                SimulationProjet.STATUS_CANCELLED,
                SimulationProjet.STATUS_VALID,
            ),
        ).exists():
            continue
        # create new SimulationProjet:
        asked_amount = projet.dossier_ds.demande_montant or 0
        try:
            taux = asked_amount / projet.assiette_or_cout_total
        except ZeroDivisionError:
            taux = 0

        simulation_projet, _ = SimulationProjet.objects.get_or_create(
            projet=projet,
            enveloppe=simulation.enveloppe,
            simulation=simulation,
            defaults={"montant": asked_amount, "taux": taux},
        )
