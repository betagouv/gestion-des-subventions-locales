import datetime
import logging

import pytest

from gsl.core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from gsl.projet.tests.factories import (
    EnveloppeProjetFactory,
    ProjetFactory,
)

from ...models import Simulation, SimulationProjet
from ..factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db

CURRENT_YEAR = datetime.datetime.now().year


def test_create_or_update_simulation_projet_from_enveloppe_projet_when_no_simulation_projet_exists():
    enveloppe_projet = EnveloppeProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=1_000,
        projet__dossier_ds__finance_cout_total=10_000,
        status=ProjetStatus.ACCEPTED,
        montant=1_000,
        dotation=DOTATION_DETR,
    )
    simulation = SimulationFactory(enveloppe__dotation=DOTATION_DETR)

    simulation_projet = SimulationProjet.objects.create_or_update_for(
        enveloppe_projet, simulation
    )

    assert simulation_projet.projet == enveloppe_projet.projet
    assert simulation_projet.simulation == simulation
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 10.0
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


def test_create_or_update_simulation_projet_from_projet_when_simulation_projet_exists():
    simulation = SimulationFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=1_000,
        projet__dossier_ds__finance_cout_total=10_000,
        status=ProjetStatus.ACCEPTED,
        montant=1_000,
        dotation=simulation.enveloppe.dotation,
    )
    original_simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        simulation=simulation,
        montant=500,
        status=SimulationProjet.STATUS_PROCESSING,
    )

    simulation_projet = SimulationProjet.objects.create_or_update_for(
        enveloppe_projet, simulation
    )

    assert simulation_projet.id == original_simulation_projet.id
    assert simulation_projet.projet == enveloppe_projet.projet
    assert simulation_projet.enveloppe_projet == enveloppe_projet
    assert simulation_projet.simulation == simulation
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 10.0
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
@pytest.mark.parametrize(
    "annotations_montant_accorde, demande_montant, assiette, log",
    (
        (10_000, 100_000, 5_000, "accordé issu des annotations"),
        (None, 10_000, 5_000, "demandé"),
    ),
)
def test_get_initial_montant_from_enveloppe_projet_must_log_if_there_is_a_problem(
    dotation, annotations_montant_accorde, demande_montant, assiette, log, caplog
):
    dp = EnveloppeProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=annotations_montant_accorde
        if dotation == DOTATION_DETR
        else None,
        projet__dossier_ds__annotations_montant_accorde_dsil=annotations_montant_accorde
        if dotation == DOTATION_DSIL
        else None,
        dotation=dotation,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__demande_montant=demande_montant,
        assiette=assiette,
    )
    with caplog.at_level(logging.WARNING):
        montant = SimulationProjet.objects.initial_montant_for(
            dp,
            status=SimulationProjet.STATUS_PROCESSING,
        )
    assert montant == assiette
    assert (
        f"Le projet de dotation {dp.dotation} (id: {dp.pk}) a une assiette plus petite que le montant {log}"
        in caplog.text
    )


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
@pytest.mark.parametrize(
    "field", ("assiette", "projet__dossier_ds__finance_cout_total")
)
@pytest.mark.parametrize(
    "status, assiette_or_finance_cout_total, annotations_montant_accorde , demande_montant, expected_montant",
    (
        (SimulationProjet.STATUS_DISMISSED, 1_000, 10_000, 5_000, 0),
        (SimulationProjet.STATUS_REFUSED, 1_000, 10_000, 5_000, 0),
        (SimulationProjet.STATUS_PROCESSING, 1_000, 10_000, 5_000, 1_000),
        (SimulationProjet.STATUS_PROCESSING, 10_000, 1_000, 5_000, 1_000),
        (SimulationProjet.STATUS_PROCESSING, 1_000, None, 5_000, 1_000),
        (SimulationProjet.STATUS_PROCESSING, 10_000, None, 5_000, 5_000),
        (SimulationProjet.STATUS_PROCESSING, 10_000, None, None, 0),
    ),
)
def test_get_initial_montant_from_enveloppe_projet(
    dotation,
    field,
    status,
    annotations_montant_accorde,
    assiette_or_finance_cout_total,
    demande_montant,
    expected_montant,
):
    enveloppe_projet = EnveloppeProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=annotations_montant_accorde
        if dotation == DOTATION_DETR
        else None,
        projet__dossier_ds__annotations_montant_accorde_dsil=annotations_montant_accorde
        if dotation == DOTATION_DSIL
        else None,
        dotation=dotation,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__demande_montant=demande_montant,
        assiette=assiette_or_finance_cout_total if field == "assiette" else None,
        projet__dossier_ds__finance_cout_total=(
            assiette_or_finance_cout_total
            if field == "projet__dossier_ds__finance_cout_total"
            else None
        ),
    )

    montant = SimulationProjet.objects.initial_montant_for(enveloppe_projet, status)

    assert montant == expected_montant


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
def test_get_initial_montant_from_enveloppe_projet_when_programmed(
    dotation,
):
    projet = ProjetFactory(
        dossier_ds__annotations_montant_accorde_detr=400_000_000
        if dotation == DOTATION_DETR
        else None,
        dossier_ds__annotations_montant_accorde_dsil=400_000_000
        if dotation == DOTATION_DSIL
        else None,
        dossier_ds__finance_cout_total=100_000_000,
        dossier_ds__demande_montant=100_202_500,
    )
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=dotation, status=ProjetStatus.ACCEPTED, montant=500
    )

    montant = SimulationProjet.objects.initial_montant_for(
        enveloppe_projet,
        SimulationProjet.STATUS_PROCESSING,  # status not coherent, but must work nevertheless
    )

    assert montant == 500


@pytest.mark.parametrize(
    "projet_status, simulation_projet_status_expected",
    (
        (ProjetStatus.ACCEPTED, SimulationProjet.STATUS_ACCEPTED),
        (ProjetStatus.REFUSED, SimulationProjet.STATUS_REFUSED),
        (ProjetStatus.PROCESSING, SimulationProjet.STATUS_PROCESSING),
        (ProjetStatus.DISMISSED, SimulationProjet.STATUS_DISMISSED),
    ),
)
def test_get_simulation_projet_status(projet_status, simulation_projet_status_expected):
    enveloppe_projet = EnveloppeProjetFactory(status=projet_status)
    status = SimulationProjet.objects.status_for(enveloppe_projet)
    assert status == simulation_projet_status_expected


# -- reset_for_enveloppe_projet --


@pytest.fixture
def perimetres():
    arr_dijon = PerimetreArrondissementFactory()
    dep_21 = PerimetreDepartementalFactory(
        departement=arr_dijon.departement, region=arr_dijon.region
    )
    region_bfc = PerimetreRegionalFactory(region=dep_21.region)

    arr_nanterre = PerimetreArrondissementFactory()
    dep_92 = PerimetreDepartementalFactory(departement=arr_nanterre.departement)
    region_idf = PerimetreRegionalFactory(region=dep_92.region)
    return [
        arr_dijon,
        dep_21,
        region_bfc,
        arr_nanterre,
        dep_92,
        region_idf,
    ]


@pytest.fixture
def simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation(
    perimetres,
):
    """
    Pour ces 3 années, on crée ces simulations :
    |--------------+-------+-------|
    | perimetre    | DETR  | DSIL  |
    |--------------+-------+-------|
    | reg_idf      |       |   x   |
    | dep_92       |   x   |   x   |
    | arr_nanterre |   x   |   x   |
    |--------------+-------+-------|
    | reg_bfc      |       |   x   |
    | dep_21       |   x   |   x   |
    | arr_dijon    |   x   |   x   |
    |--------------+-------+-------|
    """
    arr_nanterre, dep_92, region_idf, arr_dijon, dep_21, region_bfc = perimetres
    for annee in [CURRENT_YEAR - 1, CURRENT_YEAR, CURRENT_YEAR + 1]:
        for perimetre in [
            arr_nanterre,
            dep_92,
            region_idf,
            arr_dijon,
            dep_21,
            region_bfc,
        ]:
            SimulationFactory(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DSIL,
                enveloppe__perimetre=perimetre,
            )

        for perimetre in [arr_nanterre, dep_92, arr_dijon, dep_21]:
            SimulationFactory(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DETR,
                enveloppe__perimetre=perimetre,
            )


def test_reset_for_a_programmee_dotation_stops_at_its_enveloppe_year(
    perimetres,
    simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation,
):
    arr_dijon, dep_21, *_ = perimetres

    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=ProjetStatus.ACCEPTED,
        montant=0,
        projet__dossier_ds__perimetre=arr_dijon,
    )
    assert enveloppe_projet.enveloppe.annee == CURRENT_YEAR

    SimulationProjet.objects.reset_for_enveloppe_projet(enveloppe_projet)

    # Only the current year, on arr_dijon and dep_21 since a DETR enveloppe never
    # sits on a region.
    assert enveloppe_projet.simulationprojet_set.count() == 2
    for perimetre in [dep_21, arr_dijon]:
        simulation = Simulation.objects.filter(
            enveloppe__annee=CURRENT_YEAR,
            enveloppe__dotation=DOTATION_DETR,
            enveloppe__perimetre=perimetre,
        ).first()

        simulation_projets = SimulationProjet.objects.filter(
            simulation=simulation, enveloppe_projet=enveloppe_projet
        )
        assert simulation_projets.count() == 1

        simulation_projet = simulation_projets.first()
        assert simulation_projet.enveloppe_projet == enveloppe_projet
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0

    for annee in [CURRENT_YEAR - 1, CURRENT_YEAR + 1]:
        assert (
            SimulationProjet.objects.filter(
                enveloppe_projet=enveloppe_projet,
                simulation__enveloppe__annee=annee,
            ).count()
            == 0
        )


def test_reset_for_a_processing_dotation_reaches_the_next_year(
    perimetres,
    simulations_of_previous_year_current_year_and_next_year_for_each_perimetres_and_dotation,
):
    _, dep_21, region_bfc, *_ = perimetres
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=ProjetStatus.PROCESSING,
        projet__dossier_ds__perimetre=dep_21,
    )

    SimulationProjet.objects.reset_for_enveloppe_projet(enveloppe_projet)

    # Nothing is decided yet, so no year ceiling applies.
    assert enveloppe_projet.simulationprojet_set.count() == 4
    for annee in [CURRENT_YEAR, CURRENT_YEAR + 1]:
        for perimetre in [region_bfc, dep_21]:
            simulation = Simulation.objects.filter(
                enveloppe__annee=annee,
                enveloppe__dotation=DOTATION_DSIL,
                enveloppe__perimetre=perimetre,
            ).first()

            simulation_projets = SimulationProjet.objects.filter(
                simulation=simulation, enveloppe_projet=enveloppe_projet
            )
            assert simulation_projets.count() == 1

            simulation_projet = simulation_projets.first()
            assert simulation_projet.enveloppe_projet == enveloppe_projet
            assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
            assert simulation_projet.montant == 0
            assert simulation_projet.taux == 0

    assert (
        SimulationProjet.objects.filter(
            enveloppe_projet=enveloppe_projet,
            simulation__enveloppe__annee=CURRENT_YEAR - 1,
        ).count()
        == 0
    )
