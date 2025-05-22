from datetime import UTC, datetime
from decimal import Decimal

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_demarches_simplifiees.tests.factories import DossierFactory
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.constants import DOTATION_DETR
from gsl_projet.services.dotation_projet_services import DotationProjetService
from gsl_projet.tests.factories import (
    DetrProjetFactory,
    DotationProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tasks import add_enveloppe_projets_to_simulation
from gsl_simulation.tests.factories import SimulationFactory


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
def detr_projets(
    departement_perimetre, arrondissement_perimetre
) -> list[DotationProjetFactory]:
    detr_projets = []
    for montant, assiette, state, date_traitement in (
        (1_000, 3_000, Dossier.STATE_EN_CONSTRUCTION, datetime(2024, 1, 1, tzinfo=UTC)),
        (600, None, Dossier.STATE_EN_INSTRUCTION, datetime(2023, 1, 1, tzinfo=UTC)),
        (2_000, 3_000, Dossier.STATE_ACCEPTE, datetime(2024, 1, 1, tzinfo=UTC)),
        (2_000, 4_000, Dossier.STATE_ACCEPTE, datetime(2025, 1, 1, tzinfo=UTC)),
        (1_500, None, Dossier.STATE_REFUSE, datetime(2024, 1, 1, tzinfo=UTC)),
        (1_500, None, Dossier.STATE_REFUSE, datetime(2025, 1, 1, tzinfo=UTC)),
        (6_500, None, Dossier.STATE_SANS_SUITE, datetime(2024, 1, 1, tzinfo=UTC)),
        (2_500, None, Dossier.STATE_SANS_SUITE, datetime(2025, 1, 1, tzinfo=UTC)),
    ):
        status = DotationProjetService.DOSSIER_DS_STATUS_TO_DOTATION_PROJET_STATUS[
            state
        ]
        projet = ProjetFactory(
            dossier_ds=DossierFactory(
                demande_montant=montant,
                demande_dispositif_sollicite=DOTATION_DETR,
                ds_state=state,
                ds_date_traitement=date_traitement,
            ),
            perimetre=arrondissement_perimetre,
        )
        detr_projet = DetrProjetFactory(projet=projet, status=status, assiette=assiette)
        detr_projets.append(detr_projet)
    return detr_projets


@pytest.fixture
def dsil_projets(
    departement_perimetre, arrondissement_perimetre
) -> list[DotationProjetFactory]:
    dotation_projets = []
    for montant, assiette, state, date_traitement in (
        (1_000, 4_000, Dossier.STATE_EN_CONSTRUCTION, datetime(2024, 1, 1, tzinfo=UTC)),
        (600, None, Dossier.STATE_EN_INSTRUCTION, datetime(2023, 1, 1, tzinfo=UTC)),
        (2_000, 4_000, Dossier.STATE_ACCEPTE, datetime(2024, 12, 21, tzinfo=UTC)),
        (5_000, 10_000, Dossier.STATE_ACCEPTE, datetime(2025, 1, 1, tzinfo=UTC)),
        (3_500, None, Dossier.STATE_REFUSE, datetime(2024, 12, 31, tzinfo=UTC)),
        (1_500, None, Dossier.STATE_REFUSE, datetime(2025, 1, 1, tzinfo=UTC)),
        (2_500, None, Dossier.STATE_SANS_SUITE, datetime(2024, 12, 13, tzinfo=UTC)),
        (2_500, None, Dossier.STATE_SANS_SUITE, datetime(2025, 1, 1, tzinfo=UTC)),
    ):
        status = DotationProjetService.DOSSIER_DS_STATUS_TO_DOTATION_PROJET_STATUS[
            state
        ]
        projet = ProjetFactory(
            dossier_ds=DossierFactory(
                demande_montant=montant,
                demande_dispositif_sollicite="DSIL",
                ds_state=state,
                ds_date_traitement=date_traitement,
            ),
            perimetre=arrondissement_perimetre,
        )
        dsil_projet = DsilProjetFactory(projet=projet, status=status, assiette=assiette)
        dotation_projets.append(dsil_projet)
    return dotation_projets


@pytest.mark.django_db
def test_add_enveloppe_projets_to_detr_simulation(
    detr_simulation, detr_projets, dsil_projets
):
    add_enveloppe_projets_to_simulation(detr_simulation.id)

    assert SimulationProjet.objects.count() == 5

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=detr_projets[0],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == Decimal("33.333")
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=detr_projets[1],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 600
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=detr_projets[3],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 2_000
    assert simulation_projet.taux == 50
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=detr_projets[5],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=detr_projets[7],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )


@pytest.mark.django_db
def test_add_enveloppe_projets_to_dsil_simulation(
    dsil_simulation, detr_projets, dsil_projets
):
    add_enveloppe_projets_to_simulation(dsil_simulation.id)

    assert SimulationProjet.objects.count() == 5

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=dsil_projets[0],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 25
    assert simulation_projet.enveloppe.dotation == "DSIL"

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=dsil_projets[1],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.montant == 600
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=dsil_projets[3],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert simulation_projet.montant == 5_000
    assert simulation_projet.taux == 50
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=dsil_projets[5],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        dotation_projet=dsil_projets[7],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.dotation_projet
        == simulation_projet.projet.dotationprojet_set.first()
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "demande_dispositif_sollicite, count",
    (
        ("DETR", 1),
        ("['DETR']", 1),
        ("['DETR', 'DSIL']", 1),
        ("['DETR et DSIL']", 1),
        ("DETR et DSIL", 1),
        ("['DETR', 'DSIL', 'DETR et DSIL']", 1),
        ("['DETR', 'DETR et DSIL']", 1),
        ("['', 'DETR', '', 'DETR et DSIL']", 1),
        ("['DSIL', 'DETR et DSIL']", 1),
        ("DSIL", 0),
        ("['DSIL']", 0),
    ),
)
def test_add_enveloppe_projets_to_DETR_simulation_containing_DETR_in_demande_dispositif_sollicite(
    detr_simulation,
    departement_perimetre,
    arrondissement_perimetre,
    demande_dispositif_sollicite,
    count,
):
    projet = ProjetFactory(
        dossier_ds__demande_dispositif_sollicite=demande_dispositif_sollicite,
        perimetre=arrondissement_perimetre,
    )
    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)

    add_enveloppe_projets_to_simulation(detr_simulation.id)

    assert SimulationProjet.objects.count() == count


@pytest.mark.django_db
@pytest.mark.parametrize(
    "demande_dispositif_sollicite, count",
    (
        ("DETR", 0),
        ("['DETR']", 0),
        ("['DETR', 'DSIL']", 1),
        ("['DETR et DSIL']", 1),
        ("DETR et DSIL", 1),
        ("['DETR', 'DSIL', 'DETR et DSIL']", 1),
        ("['DETR', 'DETR et DSIL']", 1),
        ("['', 'DETR', '', 'DETR et DSIL']", 1),
        ("['DSIL', 'DETR et DSIL']", 1),
        ("DSIL", 1),
        ("['DSIL']", 1),
    ),
)
def test_add_enveloppe_projets_to_DSIL_simulation_containing_DSIL_in_demande_dispositif_sollicite(
    dsil_simulation,
    departement_perimetre,
    arrondissement_perimetre,
    demande_dispositif_sollicite,
    count,
):
    projet = ProjetFactory(
        dossier_ds__demande_dispositif_sollicite=demande_dispositif_sollicite,
        perimetre=arrondissement_perimetre,
    )
    DotationProjetService.create_or_update_dotation_projet_from_projet(projet)

    add_enveloppe_projets_to_simulation(dsil_simulation.id)

    assert SimulationProjet.objects.count() == count
