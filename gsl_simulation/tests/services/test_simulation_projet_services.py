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
from gsl_projet.models import Projet
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.simulation_projet_service import SimulationProjetService
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory


@pytest.mark.django_db
@mock.patch.object(
    SimulationProjetService, "create_or_update_simulation_projet_from_projet"
)
def test_update_simulation_projets_from_projet_calls_create_or_update(
    mock_create_or_update,
):
    projet = ProjetFactory()
    simulation_projets = SimulationProjetFactory.create_batch(3, projet=projet)

    SimulationProjetService.update_simulation_projets_from_projet(projet)

    assert mock_create_or_update.call_count == 3
    for simulation_projet in simulation_projets:
        mock_create_or_update.assert_any_call(projet, simulation_projet.simulation)


@pytest.mark.django_db
def test_create_or_update_simulation_projet_from_projet_when_no_simulation_projet_exists():
    projet = ProjetFactory(
        dossier_ds__annotations_montant_accorde=1_000,
        dossier_ds__finance_cout_total=10_000,
        status=Projet.STATUS_ACCEPTED,
    )
    simulation = SimulationFactory()

    simulation_projet = (
        SimulationProjetService.create_or_update_simulation_projet_from_projet(
            projet, simulation
        )
    )

    assert simulation_projet.projet == projet
    assert simulation_projet.simulation == simulation
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 10.0
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_create_or_update_simulation_projet_from_projet_when_simulation_projet_exists():
    projet = ProjetFactory(
        dossier_ds__annotations_montant_accorde=1_000,
        dossier_ds__finance_cout_total=10_000,
        status=Projet.STATUS_ACCEPTED,
    )
    simulation = SimulationFactory()
    original_simulation_projet = SimulationProjetFactory(
        projet=projet,
        simulation=simulation,
        montant=500,
        taux=5.0,
        status=SimulationProjet.STATUS_PROCESSING,
    )

    simulation_projet = (
        SimulationProjetService.create_or_update_simulation_projet_from_projet(
            projet, simulation
        )
    )

    assert simulation_projet.id == original_simulation_projet.id
    assert simulation_projet.projet == projet
    assert simulation_projet.simulation == simulation
    assert simulation_projet.montant == 1_000
    assert simulation_projet.taux == 10.0
    assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_get_initial_montant_from_projet():
    projet_with_annotations_montant_accorde = ProjetFactory(
        dossier_ds__annotations_montant_accorde=1_000,
        dossier_ds__demande_montant=10_000,
    )
    montant = SimulationProjetService.get_initial_montant_from_projet(
        projet_with_annotations_montant_accorde
    )
    assert montant == 1_000

    projet_with_demande_montant_only = ProjetFactory(dossier_ds__demande_montant=10_000)
    montant = SimulationProjetService.get_initial_montant_from_projet(
        projet_with_demande_montant_only
    )
    assert montant == 10_000

    projet_without_anything = ProjetFactory()
    montant = SimulationProjetService.get_initial_montant_from_projet(
        projet_without_anything
    )
    assert montant == 0


@pytest.fixture
def projet():
    return ProjetFactory(assiette=1000)


@pytest.mark.django_db
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


@pytest.mark.django_db
@mock.patch(
    "gsl_simulation.services.simulation_projet_service.SimulationProjetService._refuse_a_simulation_projet"
)
def test_update_status_with_refused(mock_refuse_a_simulation_projet):
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    new_status = SimulationProjet.STATUS_REFUSED

    SimulationProjetService.update_status(simulation_projet, new_status)

    mock_refuse_a_simulation_projet.assert_called_once_with(simulation_projet)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("initial_status"),
    (SimulationProjet.STATUS_ACCEPTED, SimulationProjet.STATUS_REFUSED),
)
def test_update_status_with_processing_from_accepted_or_refused(initial_status):
    simulation_projet = SimulationProjetFactory(status=initial_status)
    new_status = SimulationProjet.STATUS_PROCESSING

    with mock.patch.object(
        SimulationProjetService, "_set_back_to_processing"
    ) as mock_set_back_a_simulation_projet_to_processing:
        SimulationProjetService.update_status(simulation_projet, new_status)

        mock_set_back_a_simulation_projet_to_processing.assert_called_once_with(
            simulation_projet
        )


@pytest.mark.django_db
def test_update_status_with_processing():
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROVISOIRE
    )
    new_status = SimulationProjet.STATUS_PROCESSING

    SimulationProjetService.update_status(simulation_projet, new_status)

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == new_status


@pytest.mark.django_db
def test_update_status_with_provisoire():
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_REFUSED, projet__status=Projet.STATUS_REFUSED
    )
    new_status = SimulationProjet.STATUS_PROVISOIRE

    SimulationProjetService.update_status(simulation_projet, new_status)

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == new_status


@pytest.mark.django_db
def test_accept_a_simulation_projet():
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    other_projet_simulation_projet = SimulationProjetFactory(
        projet=simulation_projet.projet
    )
    pp_qs = ProgrammationProjet.objects.filter(projet=simulation_projet.projet)
    assert pp_qs.count() == 0

    SimulationProjetService._accept_a_simulation_projet(simulation_projet)
    updated_simulation_projet = SimulationProjet.objects.get(pk=simulation_projet.pk)
    assert updated_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED

    pp_qs = ProgrammationProjet.objects.filter(projet=updated_simulation_projet.projet)
    assert pp_qs.count() == 1

    programmation_projet = pp_qs.first()
    assert programmation_projet.enveloppe == updated_simulation_projet.enveloppe
    assert programmation_projet.taux == updated_simulation_projet.taux
    assert programmation_projet.montant == updated_simulation_projet.montant

    updated_other_simulation_projet = SimulationProjet.objects.get(
        pk=other_projet_simulation_projet.pk
    )
    assert updated_other_simulation_projet.status == SimulationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_a_simulation_projet_has_created_a_programmation_projet_with_mother_enveloppe():
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING, simulation__enveloppe=child_enveloppe
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    SimulationProjetService.update_status(simulation_projet, new_status)

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        projet=simulation_projet.projet
    )
    assert programmation_projets_qs.count() == 1
    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe


@pytest.mark.parametrize(
    "initial_progrogrammation_status, new_projet_status, programmation_status_expected",
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
@pytest.mark.django_db
def test_accept_a_simulation_projet_has_updated_a_programmation_projet_with_mother_enveloppe(
    initial_progrogrammation_status,
    new_projet_status,
    programmation_status_expected,
):
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    projet = ProjetFactory(perimetre=child_enveloppe.perimetre)
    simulation_projet = SimulationProjetFactory(
        projet=projet,
        status=SimulationProjet.STATUS_PROCESSING,
        simulation__enveloppe=child_enveloppe,
    )
    ProgrammationProjetFactory(
        projet=simulation_projet.projet,
        enveloppe=mother_enveloppe,
        status=initial_progrogrammation_status,
    )
    programmation_projets_qs = ProgrammationProjet.objects.filter(
        projet=simulation_projet.projet
    )
    assert programmation_projets_qs.count() == 1

    SimulationProjetService.update_status(simulation_projet, new_projet_status)

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        projet=simulation_projet.projet
    )
    assert programmation_projets_qs.count() == 1

    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe
    assert programmation_projet.status == programmation_status_expected


@pytest.mark.django_db
def test_update_taux(projet):
    simulation_projet = SimulationProjetFactory(projet=projet, taux=10.0)
    new_taux = 15.0

    SimulationProjetService.update_taux(simulation_projet, new_taux)

    assert simulation_projet.taux == new_taux
    assert simulation_projet.montant == 150.0


@pytest.mark.django_db
def test_update_taux_of_accepted_montat(projet):
    simulation_projet = SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_ACCEPTED, taux=20.0
    )
    other_simulation_projet = SimulationProjetFactory(
        simulation__enveloppe=simulation_projet.enveloppe,
        projet=projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        taux=20.0,
    )
    programmation_projet = ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe,
        projet=projet,
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


@pytest.mark.django_db
def test_update_montant(projet):
    simulation_projet = SimulationProjetFactory(projet=projet, montant=1000.0)
    new_montant = 500.0

    SimulationProjetService.update_montant(simulation_projet, new_montant)

    assert simulation_projet.montant == new_montant
    assert simulation_projet.taux == 50.0


@pytest.mark.django_db
def test_update_montant_of_accepted_montant(projet):
    simulation_projet = SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_ACCEPTED, montant=1_000
    )
    other_simulation_projet = SimulationProjetFactory(
        simulation__enveloppe=simulation_projet.enveloppe,
        projet=projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=1_000,
    )
    programmation_projet = ProgrammationProjetFactory(
        enveloppe=simulation_projet.enveloppe,
        projet=projet,
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


@pytest.mark.django_db
def test_is_simulation_projet_in_perimetre_regional():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    perimetre_regional = PerimetreRegionalFactory(
        region=perimetre_arrondissement.region
    )
    projet = ProjetFactory(perimetre=perimetre_arrondissement)
    simulation_projet = SimulationProjetFactory(projet=projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            simulation_projet, perimetre_regional
        )
        is True
    )

    other_arrondissement_perimetre = PerimetreArrondissementFactory()
    other_projet = ProjetFactory(perimetre=other_arrondissement_perimetre)
    other_simulation_projet = SimulationProjetFactory(projet=other_projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            other_simulation_projet, perimetre_regional
        )
        is False
    )


@pytest.mark.django_db
def test_is_simulation_projet_in_perimetre_departemental():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    perimetre_departemental = PerimetreDepartementalFactory(
        departement=perimetre_arrondissement.departement
    )
    projet = ProjetFactory(perimetre=perimetre_arrondissement)
    simulation_projet = SimulationProjetFactory(projet=projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            simulation_projet, perimetre_departemental
        )
        is True
    )

    other_arrondissement = PerimetreArrondissementFactory()
    other_projet = ProjetFactory(perimetre=other_arrondissement)
    other_simulation_projet = SimulationProjetFactory(projet=other_projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            other_simulation_projet, perimetre_departemental
        )
        is False
    )


@pytest.mark.django_db
def test_is_simulation_projet_in_perimetre_arrondissement():
    perimetre_arrondissement = PerimetreArrondissementFactory()
    projet = ProjetFactory(perimetre=perimetre_arrondissement)
    simulation_projet = SimulationProjetFactory(projet=projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            simulation_projet, perimetre_arrondissement
        )
        is True
    )

    other_arrondissement_perimetre = PerimetreArrondissementFactory()
    other_projet = ProjetFactory(perimetre=other_arrondissement_perimetre)
    other_simulation_projet = SimulationProjetFactory(projet=other_projet)

    assert (
        SimulationProjetService.is_simulation_projet_in_perimetre(
            other_simulation_projet, perimetre_arrondissement
        )
        is False
    )


@pytest.mark.parametrize(
    "projet_status, simulation_projet_status_expected",
    (
        (Projet.STATUS_ACCEPTED, SimulationProjet.STATUS_ACCEPTED),
        (Projet.STATUS_REFUSED, SimulationProjet.STATUS_REFUSED),
        (Projet.STATUS_PROCESSING, SimulationProjet.STATUS_PROCESSING),
        (Projet.STATUS_UNANSWERED, SimulationProjet.STATUS_UNANSWERED),
    ),
)
@pytest.mark.django_db
def test_get_simulation_projet_status(projet_status, simulation_projet_status_expected):
    projet = ProjetFactory(status=projet_status)
    status = SimulationProjetService.get_simulation_projet_status(projet)
    assert status == simulation_projet_status_expected
