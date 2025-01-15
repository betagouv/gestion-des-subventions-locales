from decimal import Decimal

import pytest

from gsl_core.tests.factories import PerimetreFactory
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.models import SimulationProjet
from gsl_programmation.tasks import add_enveloppe_projets_to_simulation
from gsl_programmation.tests.factories import DetrEnveloppeFactory, SimulationFactory
from gsl_projet.tests.factories import DemandeurFactory, ProjetFactory


@pytest.fixture
def perimetre():
    return PerimetreFactory()


@pytest.fixture
def simulation(perimetre):
    return SimulationFactory(enveloppe=DetrEnveloppeFactory(perimetre=perimetre))


@pytest.fixture
def detr_projets(perimetre):
    projet_with_assiette = ProjetFactory(
        dossier_ds=DossierFactory(
            demande_montant=1000,
            demande_dispositif_sollicite="DETR",
        ),
        demandeur=DemandeurFactory(
            departement=perimetre.departement,
        ),
        assiette=2000,
    )
    projet_without_assiette = ProjetFactory(
        dossier_ds=DossierFactory(
            demande_montant=600,
            demande_dispositif_sollicite="DETR",
            finance_cout_total=3000,
        ),
        demandeur=DemandeurFactory(
            departement=perimetre.departement,
        ),
    )
    return [projet_with_assiette, projet_without_assiette]


@pytest.mark.django_db
def test_add_enveloppe_projets_to_simulation(simulation, detr_projets):
    add_enveloppe_projets_to_simulation(simulation.id)

    simulation_projet = SimulationProjet.objects.filter(
        projet=detr_projets[0], enveloppe=simulation.enveloppe, simulation=simulation
    ).first()

    assert simulation_projet is not None
    assert simulation_projet.montant == 1000
    assert simulation_projet.taux == 0.5

    simulation_projet = SimulationProjet.objects.filter(
        projet=detr_projets[1], enveloppe=simulation.enveloppe, simulation=simulation
    ).first()

    assert simulation_projet is not None
    assert simulation_projet.montant == 600
    assert simulation_projet.taux == Decimal("0.2")
