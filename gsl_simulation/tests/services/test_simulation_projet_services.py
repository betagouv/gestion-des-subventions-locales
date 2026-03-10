import logging

import pytest

from gsl_programmation.tests.factories import (
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import (
    DotationProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.simulation_projet_service import SimulationProjetService
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


def test_create_or_update_simulation_projet_from_dotation_projet_when_no_simulation_projet_exists():
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=1_000,
        projet__dossier_ds__finance_cout_total=10_000,
        status=PROJET_STATUS_ACCEPTED,
        dotation=DOTATION_DETR,
    )
    simulation = SimulationFactory(enveloppe__dotation=DOTATION_DETR)

    simulation_projet = (
        SimulationProjetService.create_or_update_simulation_projet_from_dotation_projet(
            dotation_projet, simulation
        )
    )

    assert simulation_projet.projet == dotation_projet.projet
    assert simulation_projet.simulation == simulation
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 10.0
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


def test_create_or_update_simulation_projet_from_projet_when_simulation_projet_exists():
    simulation = SimulationFactory()
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=1_000,
        projet__dossier_ds__finance_cout_total=10_000,
        status=PROJET_STATUS_ACCEPTED,
        dotation=simulation.enveloppe.dotation,
    )
    original_simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        simulation=simulation,
        montant=500,
        status=SimulationProjet.STATUS_PROCESSING,
    )

    simulation_projet = (
        SimulationProjetService.create_or_update_simulation_projet_from_dotation_projet(
            dotation_projet, simulation
        )
    )

    assert simulation_projet.id == original_simulation_projet.id
    assert simulation_projet.projet == dotation_projet.projet
    assert simulation_projet.dotation_projet == dotation_projet
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
def test_get_initial_montant_from_dotation_projet_must_log_if_there_is_a_problem(
    dotation, annotations_montant_accorde, demande_montant, assiette, log, caplog
):
    dp = DotationProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=annotations_montant_accorde
        if dotation == DOTATION_DETR
        else None,
        projet__dossier_ds__annotations_montant_accorde_dsil=annotations_montant_accorde
        if dotation == DOTATION_DSIL
        else None,
        dotation=dotation,
        projet__dossier_ds__demande_montant=demande_montant,
        assiette=assiette,
    )
    with caplog.at_level(logging.WARNING):
        montant = SimulationProjetService.get_initial_montant_from_dotation_projet(
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
def test_get_initial_montant_from_dotation_projet(
    dotation,
    field,
    status,
    annotations_montant_accorde,
    assiette_or_finance_cout_total,
    demande_montant,
    expected_montant,
):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__annotations_montant_accorde_detr=annotations_montant_accorde
        if dotation == DOTATION_DETR
        else None,
        projet__dossier_ds__annotations_montant_accorde_dsil=annotations_montant_accorde
        if dotation == DOTATION_DSIL
        else None,
        dotation=dotation,
        projet__dossier_ds__demande_montant=demande_montant,
        assiette=assiette_or_finance_cout_total if field == "assiette" else None,
        projet__dossier_ds__finance_cout_total=(
            assiette_or_finance_cout_total
            if field == "projet__dossier_ds__finance_cout_total"
            else None
        ),
    )

    montant = SimulationProjetService.get_initial_montant_from_dotation_projet(
        dotation_projet, status
    )

    assert montant == expected_montant


@pytest.mark.parametrize("dotation", (DOTATION_DETR, DOTATION_DSIL))
def test_get_initial_montant_from_dotation_projet_with_an_accepted_programmation_projet(
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
    dotation_projet = DotationProjetFactory(projet=projet, dotation=dotation)
    ProgrammationProjetFactory(dotation_projet=dotation_projet, montant=500)

    montant = SimulationProjetService.get_initial_montant_from_dotation_projet(
        dotation_projet,
        SimulationProjet.STATUS_PROCESSING,  # status not coherent, but must work nevertheless
    )

    assert montant == 500


@pytest.mark.parametrize(
    "projet_status, simulation_projet_status_expected",
    (
        (PROJET_STATUS_ACCEPTED, SimulationProjet.STATUS_ACCEPTED),
        (PROJET_STATUS_REFUSED, SimulationProjet.STATUS_REFUSED),
        (PROJET_STATUS_PROCESSING, SimulationProjet.STATUS_PROCESSING),
        (PROJET_STATUS_DISMISSED, SimulationProjet.STATUS_DISMISSED),
    ),
)
def test_get_simulation_projet_status(projet_status, simulation_projet_status_expected):
    dotation_projet = DotationProjetFactory(status=projet_status)
    status = SimulationProjetService.get_simulation_projet_status(dotation_projet)
    assert status == simulation_projet_status_expected
