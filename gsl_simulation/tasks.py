from celery import shared_task

from gsl_demarches_simplifiees.models import Dossier
from gsl_projet.models import Projet
from gsl_simulation.models import Simulation, SimulationProjet

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
        asked_amount = projet.dossier_ds.demande_montant or 0
        try:
            taux = asked_amount * 100 / projet.assiette_or_cout_total
        except (ZeroDivisionError, TypeError):
            taux = 0

        simulation_projet, _ = SimulationProjet.objects.get_or_create(
            projet=projet,
            enveloppe=simulation.enveloppe,
            simulation=simulation,
            defaults={
                "montant": asked_amount,
                "taux": taux,
                "status": STATUS_MAPPINGS[projet.dossier_ds.ds_state],
            },
        )
