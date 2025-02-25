from decimal import Decimal

import pytest

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory

from ..models import Projet

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.django_db
def test_accept_projet_without_simulation_projet():
    projet = ProjetFactory(assiette=10_000)
    assert projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2025)

    projet.accept(montant=5_000, enveloppe=enveloppe)
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        projet=projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    assert simulation_projets.count() == 0

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 50
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_projet():
    projet = ProjetFactory(assiette=10_000)
    assert projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_PROVISOIRE, montant=1_000
    )
    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_REFUSED, montant=2_000
    )
    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_PROCESSING, montant=3_000
    )
    assert SimulationProjet.objects.filter(projet=projet).count() == 3

    enveloppe = DetrEnveloppeFactory(annee=2025)

    projet.accept(montant=5_000, enveloppe=enveloppe)
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        projet=projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 5_000
        assert simulation_projet.taux == 50

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 50
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_projet_update_programmation_projet():
    projet = ProjetFactory(assiette=9_000, status=Projet.STATUS_REFUSED)

    enveloppe = DetrEnveloppeFactory(annee=2025)
    ProgrammationProjetFactory(
        projet=projet,
        enveloppe=enveloppe,
        montant=0,
        status=ProgrammationProjet.STATUS_REFUSED,
    )

    projet.accept(montant=5_000, enveloppe=enveloppe)
    projet.save()
    projet.refresh_from_db()
    assert projet.status == Projet.STATUS_ACCEPTED

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == Decimal("55.56")
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


@pytest.mark.django_db
def test_accept_projet_select_parent_enveloppe():
    projet = ProjetFactory(assiette=9_000, status=Projet.STATUS_PROCESSING)
    parent_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=parent_enveloppe)
    projet.accept(montant=5_000, enveloppe=child_enveloppe)

    programmation_projets = ProgrammationProjet.objects.filter(projet=projet)

    assert programmation_projets.count() == 1
    assert programmation_projets.first().enveloppe == parent_enveloppe
