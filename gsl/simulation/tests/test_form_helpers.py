from datetime import UTC, datetime
from decimal import Decimal

import pytest

from gsl.projet.constants import (
    DOTATION_DETR,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl.projet.services.enveloppe_projet_services import EnveloppeProjetService
from gsl.projet.tests.factories import (
    DetrProjetFactory,
    DsilProjetFactory,
    EnveloppeProjetFactory,
    ProjetFactory,
)
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

from ..forms import _add_enveloppe_projets_to_simulation
from ..models import SimulationProjet
from .factories import SimulationFactory

CURRENT_YEAR = datetime.now(tz=UTC).year


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


DOSSIER_DS_STATUS_TO_ENVELOPPE_PROJET_STATUS = {
    Dossier.STATE_ACCEPTE: PROJET_STATUS_ACCEPTED,
    Dossier.STATE_EN_CONSTRUCTION: PROJET_STATUS_PROCESSING,
    Dossier.STATE_EN_INSTRUCTION: PROJET_STATUS_PROCESSING,
    Dossier.STATE_REFUSE: PROJET_STATUS_REFUSED,
    Dossier.STATE_SANS_SUITE: PROJET_STATUS_DISMISSED,
}


@pytest.fixture
def detr_projets(
    departement_perimetre, arrondissement_perimetre
) -> list[EnveloppeProjetFactory]:
    detr_projets = []
    for montant_demande, montant_accorde, assiette, state, date_traitement in (
        (
            1_000,
            None,
            3_000,
            Dossier.STATE_EN_CONSTRUCTION,
            datetime(CURRENT_YEAR - 1, 1, 1, tzinfo=UTC),
        ),
        (
            600,
            None,
            None,
            Dossier.STATE_EN_INSTRUCTION,
            datetime(CURRENT_YEAR - 2, 1, 1, tzinfo=UTC),
        ),
        (
            2_000,
            2_000,
            3_000,
            Dossier.STATE_ACCEPTE,
            datetime(CURRENT_YEAR - 1, 1, 1, tzinfo=UTC),
        ),
        (
            2_000,
            2_000,
            4_000,
            Dossier.STATE_ACCEPTE,
            datetime(CURRENT_YEAR, 1, 1, tzinfo=UTC),
        ),
        (
            1_500,
            0,
            None,
            Dossier.STATE_REFUSE,
            datetime(CURRENT_YEAR - 1, 1, 1, tzinfo=UTC),
        ),
        (
            1_500,
            0,
            None,
            Dossier.STATE_REFUSE,
            datetime(CURRENT_YEAR, 1, 1, tzinfo=UTC),
        ),
        (
            6_500,
            0,
            None,
            Dossier.STATE_SANS_SUITE,
            datetime(CURRENT_YEAR - 1, 1, 1, tzinfo=UTC),
        ),
        (
            2_500,
            0,
            None,
            Dossier.STATE_SANS_SUITE,
            datetime(CURRENT_YEAR, 1, 1, tzinfo=UTC),
        ),
    ):
        status = DOSSIER_DS_STATUS_TO_ENVELOPPE_PROJET_STATUS[state]
        projet = ProjetFactory(
            dossier_ds=DossierFactory(
                demande_montant=montant_demande,
                demande_dispositif_sollicite=DOTATION_DETR,
                ds_state=state,
                ds_date_traitement=date_traitement,
                perimetre=arrondissement_perimetre,
            ),
        )
        detr_projet = DetrProjetFactory(
            projet=projet, status=status, assiette=assiette, montant=montant_accorde
        )
        detr_projets.append(detr_projet)
    return detr_projets


@pytest.fixture
def dsil_projets(
    departement_perimetre, arrondissement_perimetre
) -> list[EnveloppeProjetFactory]:
    enveloppe_projets = []
    for montant_demande, montant_accorde, assiette, state, date_traitement in (
        (
            1_000,
            None,
            4_000,
            Dossier.STATE_EN_CONSTRUCTION,
            datetime(CURRENT_YEAR - 1, 1, 1, tzinfo=UTC),
        ),
        (
            600,
            None,
            None,
            Dossier.STATE_EN_INSTRUCTION,
            datetime(CURRENT_YEAR - 2, 1, 1, tzinfo=UTC),
        ),
        (
            2_000,
            2_000,
            4_000,
            Dossier.STATE_ACCEPTE,
            datetime(CURRENT_YEAR - 1, 12, 21, tzinfo=UTC),
        ),
        (
            5_000,
            5_000,
            10_000,
            Dossier.STATE_ACCEPTE,
            datetime(CURRENT_YEAR, 1, 1, tzinfo=UTC),
        ),
        (
            3_500,
            0,
            None,
            Dossier.STATE_REFUSE,
            datetime(CURRENT_YEAR - 1, 12, 31, tzinfo=UTC),
        ),
        (
            1_500,
            0,
            None,
            Dossier.STATE_REFUSE,
            datetime(CURRENT_YEAR, 1, 1, tzinfo=UTC),
        ),
        (
            2_500,
            0,
            None,
            Dossier.STATE_SANS_SUITE,
            datetime(CURRENT_YEAR - 1, 12, 13, tzinfo=UTC),
        ),
        (
            2_500,
            0,
            None,
            Dossier.STATE_SANS_SUITE,
            datetime(CURRENT_YEAR, 1, 1, tzinfo=UTC),
        ),
    ):
        status = DOSSIER_DS_STATUS_TO_ENVELOPPE_PROJET_STATUS[state]
        projet = ProjetFactory(
            dossier_ds=DossierFactory(
                demande_montant=montant_demande,
                demande_dispositif_sollicite="DSIL",
                ds_state=state,
                ds_date_traitement=date_traitement,
                perimetre=arrondissement_perimetre,
            ),
        )
        dsil_projet = DsilProjetFactory(
            projet=projet, status=status, assiette=assiette, montant=montant_accorde
        )
        enveloppe_projets.append(dsil_projet)
    return enveloppe_projets


@pytest.mark.django_db
def test_add_enveloppe_projets_to_detr_simulation(
    detr_simulation, detr_projets, dsil_projets
):
    _add_enveloppe_projets_to_simulation(detr_simulation)

    assert SimulationProjet.objects.count() == 5

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=detr_projets[0],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 1_000
    assert round(simulation_projet.taux, 4) == Decimal("33.3333")
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=detr_projets[1],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 600
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=detr_projets[3],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 2_000
    assert simulation_projet.taux == 50
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=detr_projets[5],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=detr_projets[7],
        simulation=detr_simulation,
    )
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
    assert simulation_projet.enveloppe.dotation == DOTATION_DETR
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )


@pytest.mark.django_db
def test_add_enveloppe_projets_to_dsil_simulation(
    dsil_simulation, detr_projets, dsil_projets
):
    _add_enveloppe_projets_to_simulation(dsil_simulation)

    assert SimulationProjet.objects.count() == 5

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=dsil_projets[0],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 25
    assert simulation_projet.enveloppe.dotation == "DSIL"

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=dsil_projets[1],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
    assert simulation_projet.montant == 600
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=dsil_projets[3],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
    assert simulation_projet.montant == 5_000
    assert simulation_projet.taux == 50
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=dsil_projets[5],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
    )

    simulation_projet = SimulationProjet.objects.get(
        enveloppe_projet=dsil_projets[7],
        simulation=dsil_simulation,
    )
    assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
    assert simulation_projet.montant == 0
    assert simulation_projet.taux == 0
    assert simulation_projet.enveloppe.dotation == "DSIL"
    assert (
        simulation_projet.enveloppe_projet
        == simulation_projet.projet.enveloppeprojet_set.first()
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
        dossier_ds__perimetre=arrondissement_perimetre,
    )
    EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet(projet)

    _add_enveloppe_projets_to_simulation(detr_simulation)

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
        dossier_ds__perimetre=arrondissement_perimetre,
    )
    EnveloppeProjetService.create_or_update_enveloppe_projet_from_projet(projet)

    _add_enveloppe_projets_to_simulation(dsil_simulation)

    assert SimulationProjet.objects.count() == count
