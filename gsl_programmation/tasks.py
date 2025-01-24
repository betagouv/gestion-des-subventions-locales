from datetime import UTC

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import Simulation, SimulationProjet
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
    for projet in (
        Projet.objects.for_perimetre(simulation_perimetre)
        .filter(dossier_ds__demande_dispositif_sollicite=simulation_dotation)
        .filter(
            Q(
                dossier_ds__ds_state__in=[
                    Dossier.STATE_EN_CONSTRUCTION,
                    Dossier.STATE_EN_INSTRUCTION,
                ]
            )
            | Q(
                dossier_ds__ds_state__in=[
                    Dossier.STATE_ACCEPTE,
                    Dossier.STATE_SANS_SUITE,
                    Dossier.STATE_REFUSE,
                ],
                dossier_ds__ds_date_traitement__gte=timezone.datetime(
                    2025, 1, 1, tzinfo=UTC
                ),
            )
        )
        .all()
    ):
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
