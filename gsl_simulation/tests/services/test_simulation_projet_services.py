import logging
from typing import cast
from unittest import mock

import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import (
    CollegueFactory,
)
from gsl_programmation.models import ProgrammationProjet
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
    DetrProjetFactory,
    DotationProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.simulation_projet_service import SimulationProjetService
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> Collegue:
    return cast(Collegue, CollegueFactory())


@mock.patch.object(
    SimulationProjetService, "create_or_update_simulation_projet_from_dotation_projet"
)
def test_update_simulation_projets_from_dotation_projet_calls_create_or_update(
    mock_create_or_update,
):
    dotation_projet = DetrProjetFactory()
    simulation_projets = SimulationProjetFactory.create_batch(
        3,
        dotation_projet=dotation_projet,
    )

    SimulationProjetService.update_simulation_projets_from_dotation_projet(
        dotation_projet
    )

    assert mock_create_or_update.call_count == 3
    for simulation_projet in simulation_projets:
        mock_create_or_update.assert_any_call(
            dotation_projet, simulation_projet.simulation
        )


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


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_accept_a_simulation_projet(mock_ds_update, user):
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    other_projet_simulation_projet = SimulationProjetFactory(
        dotation_projet=simulation_projet.dotation_projet
    )
    pp_qs = ProgrammationProjet.objects.filter(
        dotation_projet=simulation_projet.dotation_projet
    )
    assert pp_qs.count() == 0

    SimulationProjetService.accept_a_simulation_projet(simulation_projet, user)

    mock_ds_update.assert_called_once_with(
        dossier=simulation_projet.projet.dossier_ds,
        user=user,
        annotations_dotation_to_update=simulation_projet.dotation,
        dotations_to_be_checked=[simulation_projet.dotation],
        assiette=simulation_projet.dotation_projet.assiette,
        montant=simulation_projet.montant,
        taux=simulation_projet.taux,
    )

    updated_simulation_projet = SimulationProjet.objects.get(pk=simulation_projet.pk)
    assert updated_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED

    pp_qs = ProgrammationProjet.objects.filter(
        dotation_projet=updated_simulation_projet.dotation_projet
    )
    assert pp_qs.count() == 1

    programmation_projet = pp_qs.first()
    assert (
        programmation_projet.enveloppe
        == updated_simulation_projet.enveloppe.delegation_root
    )  # ProgrammationProjet must not be created with delegated enveloppe
    assert programmation_projet.taux == updated_simulation_projet.taux
    assert programmation_projet.montant == updated_simulation_projet.montant

    updated_other_simulation_projet = SimulationProjet.objects.get(
        pk=other_projet_simulation_projet.pk
    )
    assert updated_other_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_taux(field_name, user):
    dotation_projet = DotationProjetFactory(
        **{field_name: 1000},
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        montant=100,
    )
    new_taux = 15.0

    SimulationProjetService.update_taux(simulation_projet, new_taux, user)

    assert simulation_projet.taux == new_taux
    assert simulation_projet.montant == 150.0


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_taux_of_accepted_montant(mock_ds_update, field_name, user):
    dotation_projet = DotationProjetFactory(
        **{field_name: 1000},
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=200,
    )
    other_simulation_projet = SimulationProjetFactory(
        simulation__enveloppe=simulation_projet.enveloppe,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=200,
    )
    programmation_projet = ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe.delegation_root,
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
    )

    new_taux = 15.0
    SimulationProjetService.update_taux(simulation_projet, new_taux, user)

    expected_montant = 150.0
    mock_ds_update.assert_called_once_with(
        dossier=simulation_projet.projet.dossier_ds,
        user=user,
        annotations_dotation_to_update=simulation_projet.dotation,
        dotations_to_be_checked=[simulation_projet.dotation],
        assiette=simulation_projet.dotation_projet.assiette,
        montant=expected_montant,
        taux=new_taux,
    )

    assert simulation_projet.taux == new_taux
    assert simulation_projet.montant == expected_montant

    other_simulation_projet.refresh_from_db()
    assert other_simulation_projet.taux == new_taux
    assert other_simulation_projet.montant == expected_montant

    programmation_projet.refresh_from_db()
    assert programmation_projet.taux == new_taux
    assert programmation_projet.montant == expected_montant


@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_montant(field_name, user):
    dotation_projet = DotationProjetFactory(
        **{field_name: 1000},
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        montant=1000.0,
    )
    new_montant = 500.0

    SimulationProjetService.update_montant(simulation_projet, new_montant, user)

    assert simulation_projet.montant == new_montant
    assert simulation_projet.taux == 50.0


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_montant_of_accepted_montant(mock_ds_update, field_name, user):
    dotation_projet = DotationProjetFactory(
        **{field_name: 1000},
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )
    other_simulation_projet = SimulationProjetFactory(
        simulation__enveloppe=simulation_projet.enveloppe,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )
    programmation_projet = ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe.delegation_root,
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )

    new_montant = 500.0
    new_taux = 50.0

    SimulationProjetService.update_montant(simulation_projet, new_montant, user)

    mock_ds_update.assert_called_once_with(
        dossier=simulation_projet.projet.dossier_ds,
        user=user,
        annotations_dotation_to_update=simulation_projet.dotation,
        dotations_to_be_checked=[simulation_projet.dotation],
        assiette=simulation_projet.dotation_projet.assiette,
        montant=new_montant,
        taux=new_taux,
    )

    assert simulation_projet.montant == new_montant
    assert simulation_projet.taux == new_taux

    other_simulation_projet.refresh_from_db()
    assert other_simulation_projet.montant == new_montant
    assert other_simulation_projet.taux == new_taux

    programmation_projet.refresh_from_db()
    assert programmation_projet.montant == new_montant
    assert programmation_projet.taux == new_taux


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


@mock.patch("gsl_projet.models.DotationProjet.accept")
def test_accept_simulation_projet_triggers_transition(
    mock_transition_dotation_projet,
    user,
):
    simulation_projet = SimulationProjetFactory()

    SimulationProjetService.accept_a_simulation_projet(simulation_projet, user)

    kwargs = {
        "enveloppe": simulation_projet.enveloppe,
        "montant": simulation_projet.montant,
        "user": user,
    }
    mock_transition_dotation_projet.assert_called_once_with(**kwargs)
