from celery import shared_task

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import Simulation, SimulationProjet
from gsl_programmation.services import ProjetService
from gsl_projet.models import Projet

STATUS_MAPPINGS = {
    Dossier.STATE_ACCEPTE: SimulationProjet.STATUS_VALID,
    Dossier.STATE_SANS_SUITE: SimulationProjet.STATUS_CANCELLED,
    Dossier.STATE_REFUSE: SimulationProjet.STATUS_CANCELLED,
    Dossier.STATE_EN_CONSTRUCTION: SimulationProjet.STATUS_DRAFT,
    Dossier.STATE_EN_INSTRUCTION: SimulationProjet.STATUS_DRAFT,
}


@shared_task
def add_enveloppe_projets_to_simulation(simulation_id):
    simulation = Simulation.objects.get(id=simulation_id)
    simulation_perimetre = simulation.enveloppe.perimetre
    simulation_dotation = simulation.enveloppe.type
    # todo later: "simulation par arrondissement"
    selected_projets = Projet.objects.for_perimetre(simulation_perimetre).filter(
        dossier_ds__demande_dispositif_sollicite=simulation_dotation
    )
    selected_projets = (
        ProjetService.filter_projet_qs_to_keep_only_projet_to_deal_with_this_year(
            selected_projets
        )
    )

    for projet in selected_projets:
        asked_amount = projet.dossier_ds.demande_montant or 0
        try:
            taux = asked_amount / projet.assiette_or_cout_total
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
