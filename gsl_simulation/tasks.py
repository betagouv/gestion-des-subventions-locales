from celery import shared_task

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.models import Projet
from gsl_simulation.models import Simulation, SimulationProjet
from gsl_simulation.services.simulation_projet_service import SimulationProjetService

STATUS_MAPPINGS = {
    Dossier.STATE_ACCEPTE: SimulationProjet.STATUS_ACCEPTED,
    Dossier.STATE_SANS_SUITE: SimulationProjet.STATUS_REFUSED,
    Dossier.STATE_REFUSE: SimulationProjet.STATUS_REFUSED,
    Dossier.STATE_EN_CONSTRUCTION: SimulationProjet.STATUS_PROCESSING,
    Dossier.STATE_EN_INSTRUCTION: SimulationProjet.STATUS_PROCESSING,
}


@shared_task
def add_enveloppe_projets_to_simulation(simulation_id):
    simulation = Simulation.objects.get(id=simulation_id)
    simulation_perimetre = simulation.enveloppe.perimetre
    simulation_dotation = simulation.enveloppe.type
    # todo later: "simulation par arrondissement"
    selected_projets = Projet.objects.for_perimetre(simulation_perimetre).filter(
        dossier_ds__demande_dispositif_sollicite__contains=simulation_dotation
    )
    selected_projets = selected_projets.for_current_year()

    for projet in selected_projets:
        SimulationProjetService.create_or_update_simulation_projet_from_projet(
            projet, simulation_id
        )
