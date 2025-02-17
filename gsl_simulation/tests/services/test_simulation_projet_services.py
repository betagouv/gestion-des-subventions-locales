from unittest import mock

import pytest

from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.services.simulation_projet_service import SimulationProjetService
from gsl_simulation.tests.factories import SimulationProjetFactory


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
def test_update_status_with_other_status_than_accepted():
    simulation_projet = SimulationProjetFactory(status=SimulationProjet.STATUS_REFUSED)
    new_status = SimulationProjet.STATUS_PROCESSING

    SimulationProjetService.update_status(simulation_projet, new_status)

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
        status=SimulationProjet.STATUS_PROCESSING, enveloppe=child_enveloppe
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    SimulationProjetService.update_status(simulation_projet, new_status)

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        projet=simulation_projet.projet
    )
    assert programmation_projets_qs.count() == 1
    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe


@pytest.mark.django_db
def test_accept_a_simulation_projet_has_updated_a_programmation_projet_with_mother_enveloppe():
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    projet = ProjetFactory(demandeur__departement=child_enveloppe.perimetre.departement)
    simulation_projet = SimulationProjetFactory(
        projet=projet,
        status=SimulationProjet.STATUS_PROCESSING,
        enveloppe=child_enveloppe,
    )
    ProgrammationProjetFactory(
        projet=simulation_projet.projet,
        enveloppe=mother_enveloppe,
        status=ProgrammationProjet.STATUS_REFUSED,
    )
    programmation_projets_qs = ProgrammationProjet.objects.filter(
        projet=simulation_projet.projet
    )
    assert programmation_projets_qs.count() == 1

    new_status = SimulationProjet.STATUS_ACCEPTED
    SimulationProjetService.update_status(simulation_projet, new_status)

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        projet=simulation_projet.projet
    )
    assert programmation_projets_qs.count() == 1
    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe


@pytest.mark.django_db
def test_update_taux(projet):
    simulation_projet = SimulationProjetFactory(projet=projet, taux=10.0)
    new_taux = 15.0

    SimulationProjetService.update_taux(simulation_projet, new_taux)

    assert simulation_projet.taux == new_taux
    assert simulation_projet.montant == 150.0


@pytest.mark.django_db
def test_update_montant(projet):
    simulation_projet = SimulationProjetFactory(projet=projet, montant=1000.0)
    new_montant = 500.0

    SimulationProjetService.update_montant(simulation_projet, new_montant)

    assert simulation_projet.montant == new_montant
    assert simulation_projet.taux == 50.0
