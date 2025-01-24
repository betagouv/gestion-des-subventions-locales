from datetime import datetime
from decimal import Decimal

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.models import SimulationProjet
from gsl_programmation.tasks import add_enveloppe_projets_to_simulation
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    SimulationFactory,
)
from gsl_projet.tests.factories import DemandeurFactory, ProjetFactory


@pytest.fixture
def arrondissement_perimetre():
    return PerimetreArrondissementFactory()


@pytest.fixture
def departement_perimetre(arrondissement_perimetre):
    return PerimetreDepartementalFactory(
        departement=arrondissement_perimetre.departement
    )


@pytest.fixture
def region_perimetre(departement_perimetre):
    return PerimetreRegionalFactory(region=departement_perimetre.region)


@pytest.fixture
def detr_simulation(departement_perimetre):
    return SimulationFactory(
        enveloppe=DetrEnveloppeFactory(perimetre=departement_perimetre)
    )


@pytest.fixture
def dsil_simulation(region_perimetre):
    return SimulationFactory(enveloppe=DsilEnveloppeFactory(perimetre=region_perimetre))


@pytest.fixture
def detr_projets(departement_perimetre):
    projets = []
    for montant, assiette, state, date_traitement in [
        (1_000, 2_000, Dossier.STATE_EN_CONSTRUCTION, datetime(2024, 1, 1)),
        (600, None, Dossier.STATE_EN_INSTRUCTION, datetime(2023, 1, 1)),
        (2_000, 3_000, Dossier.STATE_ACCEPTE, datetime(2024, 1, 1)),
        (2_000, 4_000, Dossier.STATE_ACCEPTE, datetime(2025, 1, 1)),
        (1_500, None, Dossier.STATE_REFUSE, datetime(2024, 1, 1)),
        (1_500, None, Dossier.STATE_REFUSE, datetime(2025, 1, 1)),
        (6_500, 0, Dossier.STATE_SANS_SUITE, datetime(2024, 1, 1)),
        (2_500, 0, Dossier.STATE_SANS_SUITE, datetime(2025, 1, 1)),
    ]:
        projets.append(
            ProjetFactory(
                dossier_ds=DossierFactory(
                    demande_montant=montant,
                    demande_dispositif_sollicite="DETR",
                    ds_state=state,
                    ds_date_traitement=date_traitement,
                ),
                demandeur=DemandeurFactory(
                    departement=departement_perimetre.departement,
                ),
                assiette=assiette,
            )
        )

    return projets


@pytest.fixture
def dsil_projets(departement_perimetre):
    projets = []
    for montant, assiette, state, date_traitement in [
        (1_000, 2_000, Dossier.STATE_EN_CONSTRUCTION, datetime(2024, 1, 1)),
        (600, None, Dossier.STATE_EN_INSTRUCTION, datetime(2023, 1, 1)),
        (2_000, 4_000, Dossier.STATE_ACCEPTE, datetime(2024, 12, 21)),
        (5_000, 10_000, Dossier.STATE_ACCEPTE, datetime(2025, 1, 1)),
        (3_500, None, Dossier.STATE_REFUSE, datetime(2024, 12, 31)),
        (1_500, None, Dossier.STATE_REFUSE, datetime(2025, 1, 1)),
        (2_500, 0, Dossier.STATE_SANS_SUITE, datetime(2024, 12, 13)),
        (2_500, 0, Dossier.STATE_SANS_SUITE, datetime(2025, 1, 1)),
    ]:
        projets.append(
            ProjetFactory(
                dossier_ds=DossierFactory(
                    demande_montant=montant,
                    demande_dispositif_sollicite="DSIL",
                    ds_state=state,
                    ds_date_traitement=date_traitement,
                ),
                demandeur=DemandeurFactory(
                    departement=departement_perimetre.departement,
                ),
                assiette=assiette,
            )
        )
    return projets


@pytest.mark.django_db
def test_add_enveloppe_projets_to_detr_simulation(
    detr_simulation, detr_projets, dsil_projets
):
    add_enveloppe_projets_to_simulation(detr_simulation.id)

    assert SimulationProjet.objects.count() == 5

    simulation_projet = SimulationProjet.objects.get(
        projet=detr_projets[0],
        enveloppe=detr_simulation.enveloppe,
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 1000
    assert simulation_projet.taux == 0.5
    assert simulation_projet.status == SimulationProjet.STATUS_DRAFT
    assert simulation_projet.enveloppe.type == "DETR"

    simulation_projet = SimulationProjet.objects.get(
        projet=detr_projets[1],
        enveloppe=detr_simulation.enveloppe,
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 600
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_DRAFT
    assert simulation_projet.enveloppe.type == "DETR"

    simulation_projet = SimulationProjet.objects.get(
        projet=detr_projets[3],
        enveloppe=detr_simulation.enveloppe,
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 2_000
    assert simulation_projet.taux == Decimal("0.5")
    assert simulation_projet.status == SimulationProjet.STATUS_VALID
    assert simulation_projet.enveloppe.type == "DETR"

    simulation_projet = SimulationProjet.objects.get(
        projet=detr_projets[5],
        enveloppe=detr_simulation.enveloppe,
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 1_500
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_CANCELLED
    assert simulation_projet.enveloppe.type == "DETR"

    simulation_projet = SimulationProjet.objects.get(
        projet=detr_projets[7],
        enveloppe=detr_simulation.enveloppe,
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 2_500
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_CANCELLED
    assert simulation_projet.enveloppe.type == "DETR"


@pytest.mark.django_db
def test_add_enveloppe_projets_to_dsil_simulation(
    dsil_simulation, detr_projets, dsil_projets
):
    add_enveloppe_projets_to_simulation(dsil_simulation.id)

    assert SimulationProjet.objects.count() == 5

    simulation_projet = SimulationProjet.objects.get(
        projet=dsil_projets[0],
        enveloppe=dsil_simulation.enveloppe,
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_DRAFT
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 0.5
    assert simulation_projet.enveloppe.type == "DSIL"

    simulation_projet = SimulationProjet.objects.get(
        projet=dsil_projets[1],
        enveloppe=dsil_simulation.enveloppe,
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_DRAFT
    assert simulation_projet.montant == 600
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.type == "DSIL"

    simulation_projet = SimulationProjet.objects.get(
        projet=dsil_projets[3],
        enveloppe=dsil_simulation.enveloppe,
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_VALID
    assert simulation_projet.montant == 5_000
    assert simulation_projet.taux == Decimal("0.5")
    assert simulation_projet.enveloppe.type == "DSIL"

    simulation_projet = SimulationProjet.objects.get(
        projet=dsil_projets[5],
        enveloppe=dsil_simulation.enveloppe,
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_CANCELLED
    assert simulation_projet.montant == 1_500
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.type == "DSIL"

    simulation_projet = SimulationProjet.objects.get(
        projet=dsil_projets[7],
        enveloppe=dsil_simulation.enveloppe,
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_CANCELLED
    assert simulation_projet.montant == 2_500
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.type == "DSIL"
