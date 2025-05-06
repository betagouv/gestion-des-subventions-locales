import logging
from unittest import mock

import pytest

from gsl_core.tests.factories import (
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
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
        projet__dossier_ds__annotations_montant_accorde=1_000,
        projet__dossier_ds__finance_cout_total=10_000,
        projet__status=PROJET_STATUS_ACCEPTED,
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
        projet__dossier_ds__annotations_montant_accorde=1_000,
        projet__dossier_ds__finance_cout_total=10_000,
        status=PROJET_STATUS_ACCEPTED,
        dotation=simulation.enveloppe.dotation,
    )
    original_simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        simulation=simulation,
        montant=500,
        taux=5.0,
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


@pytest.mark.parametrize(
    "annotations_montant_accorde, demande_montant, assiette, log",
    (
        (10_000, 100_000, 5_000, "accordé issu des annotations"),
        (None, 10_000, 5_000, "demandé"),
    ),
)
def test_get_initial_montant_from_dotation_projet_must_log_if_there_is_a_problem(
    annotations_montant_accorde, demande_montant, assiette, log, caplog
):
    dp = DotationProjetFactory(
        projet__dossier_ds__annotations_montant_accorde=annotations_montant_accorde,
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
    field,
    status,
    annotations_montant_accorde,
    assiette_or_finance_cout_total,
    demande_montant,
    expected_montant,
):
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__annotations_montant_accorde=annotations_montant_accorde,
        projet__dossier_ds__demande_montant=demande_montant,
        assiette=assiette_or_finance_cout_total if field == "assiette" else None,
        projet__dossier_ds__finance_cout_total=assiette_or_finance_cout_total
        if field == "projet__dossier_ds__finance_cout_total"
        else None,
    )

    montant = SimulationProjetService.get_initial_montant_from_dotation_projet(
        dotation_projet, status
    )

    assert montant == expected_montant


def test_get_initial_montant_from_dotation_projet_with_an_accepted_programmation_projet():
    projet = ProjetFactory(
        dossier_ds__annotations_montant_accorde=400_000_000,
        dossier_ds__finance_cout_total=100_000_000,
        dossier_ds__demande_montant=100_202_500,
    )
    dotation_projet = DotationProjetFactory(projet=projet)
    ProgrammationProjetFactory(dotation_projet=dotation_projet, montant=500)

    montant = SimulationProjetService.get_initial_montant_from_dotation_projet(
        dotation_projet,
        SimulationProjet.STATUS_PROCESSING,  # status not coherent, but must work nevertheless
    )

    assert montant == 500


@pytest.fixture
def dotation_projet():
    return DotationProjetFactory(assiette=1000)


@mock.patch(
    "gsl_simulation.services.simulation_projet_service.SimulationProjetService._accept_a_simulation_projet"
)
def test_update_status_with_accepted(mock_accept_a_simulation_projet):
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    SimulationProjetService.update_status(simulation_projet, new_status)

    mock_accept_a_simulation_projet.assert_called_once_with(simulation_projet)


def test_update_status_with_refused():
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    new_status = SimulationProjet.STATUS_REFUSED

    with mock.patch.object(
        SimulationProjetService, "_refuse_a_simulation_projet"
    ) as mock_refuse_a_simulation_projet:
        SimulationProjetService.update_status(simulation_projet, new_status)

        mock_refuse_a_simulation_projet.assert_called_once_with(simulation_projet)


def test_update_status_with_dismissed():
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    new_status = SimulationProjet.STATUS_DISMISSED

    with mock.patch.object(
        SimulationProjetService, "_dismiss_a_simulation_projet"
    ) as mock_dismiss_a_simulation_projet:
        SimulationProjetService.update_status(simulation_projet, new_status)

        mock_dismiss_a_simulation_projet.assert_called_once_with(simulation_projet)


@pytest.mark.parametrize(
    ("initial_status"),
    (
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_DISMISSED,
    ),
)
def test_update_status_with_processing_from_accepted_or_refused_or_dismissed(
    initial_status,
):
    simulation_projet = SimulationProjetFactory(status=initial_status)
    new_status = SimulationProjet.STATUS_PROCESSING

    with mock.patch.object(
        SimulationProjetService, "_set_back_to_processing"
    ) as mock_set_back_a_simulation_projet_to_processing:
        SimulationProjetService.update_status(simulation_projet, new_status)

        mock_set_back_a_simulation_projet_to_processing.assert_called_once_with(
            simulation_projet
        )


def test_update_status_with_processing():
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROVISOIRE
    )
    new_status = SimulationProjet.STATUS_PROCESSING

    SimulationProjetService.update_status(simulation_projet, new_status)

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == new_status


SIMULATION_PROJET_STATUS_TO_DOTATION_PROJET_STATUS = {
    SimulationProjet.STATUS_ACCEPTED: PROJET_STATUS_ACCEPTED,
    SimulationProjet.STATUS_REFUSED: PROJET_STATUS_REFUSED,
    SimulationProjet.STATUS_PROCESSING: PROJET_STATUS_PROCESSING,
    SimulationProjet.STATUS_DISMISSED: PROJET_STATUS_DISMISSED,
    SimulationProjet.STATUS_PROVISOIRE: PROJET_STATUS_PROCESSING,
}


@pytest.mark.parametrize(
    ("initial_status"),
    (
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_DISMISSED,
    ),
)
def test_update_status_with_provisoire_from_refused_or_accepted_or_dismissed(
    initial_status,
):
    dotation_projet = DotationProjetFactory(
        status=SIMULATION_PROJET_STATUS_TO_DOTATION_PROJET_STATUS[initial_status]
    )
    simulation_projet = SimulationProjetFactory(
        status=initial_status,
        dotation_projet=dotation_projet,
    )
    assert (
        dotation_projet.status
        == SIMULATION_PROJET_STATUS_TO_DOTATION_PROJET_STATUS[initial_status]
    )
    SimulationProjetFactory.create_batch(
        3,
        dotation_projet=dotation_projet,
        status=initial_status,
    )

    SimulationProjetService.update_status(
        simulation_projet, SimulationProjet.STATUS_PROVISOIRE
    )

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == SimulationProjet.STATUS_PROVISOIRE
    assert simulation_projet.dotation_projet.status == PROJET_STATUS_PROCESSING

    other_simulation_projets = SimulationProjet.objects.exclude(pk=simulation_projet.pk)
    assert other_simulation_projets.count() == 3
    for other_simulation_projet in other_simulation_projets:
        assert other_simulation_projet.status == SimulationProjet.STATUS_PROCESSING


@pytest.mark.parametrize(
    ("initial_status"),
    (
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
    ),
)
def test_update_status_with_provisoire_remove_programmation_projet_from_accepted_or_refused(
    initial_status,
):
    dotation_projet = DotationProjetFactory(
        status=SIMULATION_PROJET_STATUS_TO_DOTATION_PROJET_STATUS[initial_status]
    )
    simulation_projet = SimulationProjetFactory(
        status=initial_status,
        dotation_projet=dotation_projet,
    )
    ProgrammationProjetFactory(dotation_projet=simulation_projet.dotation_projet)

    SimulationProjetService.update_status(
        simulation_projet, SimulationProjet.STATUS_PROVISOIRE
    )

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == SimulationProjet.STATUS_PROVISOIRE
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=simulation_projet.dotation_projet
        ).count()
        == 0
    )


def test_accept_a_simulation_projet():
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

    SimulationProjetService._accept_a_simulation_projet(simulation_projet)
    updated_simulation_projet = SimulationProjet.objects.get(pk=simulation_projet.pk)
    assert updated_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED

    pp_qs = ProgrammationProjet.objects.filter(
        dotation_projet=updated_simulation_projet.dotation_projet
    )
    assert pp_qs.count() == 1

    programmation_projet = pp_qs.first()
    assert programmation_projet.enveloppe == updated_simulation_projet.enveloppe
    assert programmation_projet.taux == updated_simulation_projet.taux
    assert programmation_projet.montant == updated_simulation_projet.montant

    updated_other_simulation_projet = SimulationProjet.objects.get(
        pk=other_projet_simulation_projet.pk
    )
    assert updated_other_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


def test_accept_a_simulation_projet_has_created_a_programmation_projet_with_mother_enveloppe():
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    simulation = SimulationFactory(enveloppe=child_enveloppe)
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING,
        simulation=simulation,
        dotation_projet__dotation=DOTATION_DETR,
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    SimulationProjetService.update_status(simulation_projet, new_status)

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        dotation_projet=simulation_projet.dotation_projet
    )
    assert programmation_projets_qs.count() == 1
    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe


@pytest.mark.parametrize(
    "initial_programmation_status, new_projet_status, programmation_status_expected",
    (
        (
            ProgrammationProjet.STATUS_REFUSED,
            SimulationProjet.STATUS_ACCEPTED,
            ProgrammationProjet.STATUS_ACCEPTED,
        ),
        (
            ProgrammationProjet.STATUS_ACCEPTED,
            SimulationProjet.STATUS_REFUSED,
            ProgrammationProjet.STATUS_REFUSED,
        ),
    ),
)
def test_accept_a_simulation_projet_has_updated_a_programmation_projet_with_mother_enveloppe(
    initial_programmation_status,
    new_projet_status,
    programmation_status_expected,
):
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    simulation = SimulationFactory(enveloppe=child_enveloppe)
    dotation_projet = DotationProjetFactory(
        projet__perimetre=child_enveloppe.perimetre, dotation=DOTATION_DETR
    )

    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        simulation=simulation,
    )
    ProgrammationProjetFactory(
        dotation_projet=simulation_projet.dotation_projet,
        enveloppe=mother_enveloppe,
        status=initial_programmation_status,
    )
    programmation_projets_qs = ProgrammationProjet.objects.filter(
        dotation_projet=simulation_projet.dotation_projet
    )
    assert programmation_projets_qs.count() == 1

    SimulationProjetService.update_status(simulation_projet, new_projet_status)

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        dotation_projet=simulation_projet.dotation_projet
    )
    assert programmation_projets_qs.count() == 1

    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe
    assert programmation_projet.status == programmation_status_expected


@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_taux(field_name):
    dotation_projet = DotationProjetFactory(
        **{field_name: 1000},
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        taux=10.0,
    )
    new_taux = 15.0

    SimulationProjetService.update_taux(simulation_projet, new_taux)

    assert simulation_projet.taux == new_taux
    assert simulation_projet.montant == 150.0


@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_taux_of_accepted_montant(field_name):
    dotation_projet = DotationProjetFactory(
        **{field_name: 1000},
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        taux=20.0,
    )
    other_simulation_projet = SimulationProjetFactory(
        simulation__enveloppe=simulation_projet.enveloppe,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        taux=20.0,
    )
    programmation_projet = ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe,
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        taux=20.0,
    )

    new_taux = 15.0
    SimulationProjetService.update_taux(simulation_projet, new_taux)

    assert simulation_projet.taux == new_taux
    assert simulation_projet.montant == 150.0

    other_simulation_projet.refresh_from_db()
    assert other_simulation_projet.taux == new_taux
    assert other_simulation_projet.montant == 150.0

    programmation_projet.refresh_from_db()
    assert programmation_projet.taux == new_taux
    assert programmation_projet.montant == 150.0


@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_montant(field_name):
    dotation_projet = DotationProjetFactory(
        **{field_name: 1000},
    )
    simulation_projet = SimulationProjetFactory(
        dotation_projet=dotation_projet,
        montant=1000.0,
    )
    new_montant = 500.0

    SimulationProjetService.update_montant(simulation_projet, new_montant)

    assert simulation_projet.montant == new_montant
    assert simulation_projet.taux == 50.0


@pytest.mark.parametrize(
    "field_name",
    ("assiette", "projet__dossier_ds__finance_cout_total"),
)
def test_update_montant_of_accepted_montant(field_name):
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
        enveloppe=simulation_projet.enveloppe,
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )

    new_montant = 500.0

    SimulationProjetService.update_montant(simulation_projet, new_montant)

    assert simulation_projet.montant == new_montant
    assert simulation_projet.taux == 50.0

    other_simulation_projet.refresh_from_db()
    assert other_simulation_projet.montant == 500.0
    assert other_simulation_projet.taux == 50.0

    programmation_projet.refresh_from_db()
    assert programmation_projet.montant == 500.0
    assert programmation_projet.taux == 50.0


def test_is_simulation_projet_in_perimetre_regional():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    perimetre_regional = PerimetreRegionalFactory(
        region=perimetre_arrondissement.region
    )
    dotation_projet = DetrProjetFactory(projet__perimetre=perimetre_arrondissement)
    simulation_projet = SimulationProjetFactory(dotation_projet=dotation_projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            simulation_projet, perimetre_regional
        )
        is True
    )

    other_arrondissement_perimetre = PerimetreArrondissementFactory()
    other_dotation_projet = DotationProjetFactory(
        projet__perimetre=other_arrondissement_perimetre, dotation=DOTATION_DETR
    )
    other_simulation_projet = SimulationProjetFactory(
        dotation_projet=other_dotation_projet
    )

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            other_simulation_projet, perimetre_regional
        )
        is False
    )


def test_is_simulation_projet_in_perimetre_departemental():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    perimetre_departemental = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement.departement
    )
    dotation_projet = DetrProjetFactory(projet__perimetre=perimetre_arrondissement)
    simulation_projet = SimulationProjetFactory(dotation_projet=dotation_projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            simulation_projet, perimetre_departemental
        )
        is True
    )

    other_arrondissement = PerimetreArrondissementFactory()
    other_dotation_projet = DetrProjetFactory(projet__perimetre=other_arrondissement)
    other_simulation_projet = SimulationProjetFactory(
        dotation_projet=other_dotation_projet
    )

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            other_simulation_projet, perimetre_departemental
        )
        is False
    )


def test_is_simulation_projet_in_perimetre_arrondissement():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    dotation_projet = DetrProjetFactory(projet__perimetre=perimetre_arrondissement)
    simulation_projet = SimulationProjetFactory(dotation_projet=dotation_projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            simulation_projet, perimetre_arrondissement
        )
        is True
    )

    other_arrondissement_perimetre = PerimetreArrondissementFactory()
    other_dotation_projet = DetrProjetFactory(
        projet__perimetre=other_arrondissement_perimetre
    )
    other_simulation_projet = SimulationProjetFactory(
        dotation_projet=other_dotation_projet
    )

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            other_simulation_projet, perimetre_arrondissement
        )
        is False
    )


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


@pytest.mark.parametrize(
    ("dotation_projet_transition, method, with_enveloppe, with_montant"),
    (
        ("accept", SimulationProjetService._accept_a_simulation_projet, True, True),
        ("refuse", SimulationProjetService._refuse_a_simulation_projet, True, False),
        ("dismiss", SimulationProjetService._dismiss_a_simulation_projet, False, False),
        (
            "set_back_status_to_processing",
            SimulationProjetService._set_back_to_processing,
            False,
            False,
        ),
    ),
)
def test_simulation_projet_transition_are_called(
    dotation_projet_transition, method, with_enveloppe, with_montant
):
    with mock.patch(
        f"gsl_projet.models.DotationProjet.{dotation_projet_transition}"
    ) as mock_transition_dotation_projet:
        simulation_projet = SimulationProjetFactory()
        args = {}
        if with_enveloppe:
            args["enveloppe"] = simulation_projet.enveloppe
        if with_montant:
            args["montant"] = simulation_projet.montant

        method(simulation_projet)

        mock_transition_dotation_projet.assert_called_once_with(**args)
