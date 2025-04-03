from decimal import Decimal

import pytest
from django_fsm import TransitionNotAllowed

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.models import Projet
from gsl_projet.tests.factories import ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_montant_retenu_with_accepted_programmation_projet():
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED, montant=10_000
    )
    projet = programmation_projet.projet
    projet.accepted_programmation_projets = [programmation_projet]
    assert projet.montant_retenu == 10_000


def test_montant_retenu_with_refused_programmation_projet():
    projet = ProjetFactory()
    assert projet.montant_retenu is None

    ProgrammationProjetFactory(
        projet=projet, status=ProgrammationProjet.STATUS_REFUSED, montant=0
    )
    assert projet.montant_retenu is None


def test_taux_retenu_with_accepted_programmation_projet():
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED, taux=10
    )
    projet = programmation_projet.projet
    projet.accepted_programmation_projets = [programmation_projet]
    assert projet.taux_retenu == 10


def test_taux_retenu_with_refused_programmation_projet():
    projet = ProjetFactory()
    assert projet.taux_retenu is None

    ProgrammationProjetFactory(
        projet=projet, status=ProgrammationProjet.STATUS_REFUSED, taux=0
    )
    assert projet.taux_retenu is None


@pytest.mark.parametrize(
    ("demande_dispositif_sollicite", "expected_is_asking_for_detr"),
    (
        ("", False),
        ("DETR", True),
        ("DSIL", False),
        ("DETR DSIL", True),
        ("['DSIL', 'DETR']", True),
    ),
)
def test_is_asking_for_detr(demande_dispositif_sollicite, expected_is_asking_for_detr):
    projet = ProjetFactory(
        dossier_ds__demande_dispositif_sollicite=demande_dispositif_sollicite
    )
    assert projet.is_asking_for_detr is expected_is_asking_for_detr


# Accept


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


def test_accept_projet_select_parent_enveloppe():
    projet = ProjetFactory(assiette=9_000, status=Projet.STATUS_PROCESSING)
    parent_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=parent_enveloppe)
    projet.accept(montant=5_000, enveloppe=child_enveloppe)

    programmation_projets = ProgrammationProjet.objects.filter(projet=projet)

    assert programmation_projets.count() == 1
    assert programmation_projets.first().enveloppe == parent_enveloppe


# Refuse


def test_refusing_a_projet_creates_one_programmation_projet():
    projet = ProjetFactory(status=Projet.STATUS_PROCESSING)
    assert projet.status == Projet.STATUS_PROCESSING
    assert projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2024)

    projet.refuse(enveloppe=enveloppe)
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_REFUSED

    programmation_projets = ProgrammationProjet.objects.filter(
        projet=projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED


def test_refusing_a_projet_updates_all_simulation_projet():
    projet = ProjetFactory(status=Projet.STATUS_PROCESSING)
    assert projet.status == Projet.STATUS_PROCESSING
    assert projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2024)

    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_PROVISOIRE, montant=1_000
    )
    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_ACCEPTED, montant=2_000
    )
    SimulationProjetFactory(
        projet=projet, status=SimulationProjet.STATUS_PROCESSING, montant=5_000
    )
    assert SimulationProjet.objects.filter(projet=projet).count() == 3

    projet.refuse(enveloppe=enveloppe)
    projet.save()
    projet.refresh_from_db()

    assert SimulationProjet.objects.filter(projet=projet).count() == 3
    simulation_projets = SimulationProjet.objects.filter(projet=projet)
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


# Set back status to processing


def test_set_back_status_to_processing_from_accepted():
    projet = ProjetFactory(status=Projet.STATUS_ACCEPTED)
    ProgrammationProjetFactory(
        projet=projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=10_000,
        taux=20,
    )
    SimulationProjetFactory.create_batch(
        3,
        projet=projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=10_000,
        taux=20,
    )

    projet.set_back_status_to_processing()
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_PROCESSING
    assert ProgrammationProjet.objects.filter(projet=projet).count() == 0
    simulation_projets = SimulationProjet.objects.filter(projet=projet)
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert simulation_projet.montant == 10_000
        assert simulation_projet.taux == 20


def test_set_back_status_to_processing_from_refused():
    projet = ProjetFactory(status=Projet.STATUS_REFUSED)
    ProgrammationProjetFactory(
        projet=projet,
        status=ProgrammationProjet.STATUS_REFUSED,
    )
    SimulationProjetFactory.create_batch(
        3, projet=projet, status=SimulationProjet.STATUS_REFUSED, montant=0, taux=0
    )

    projet.set_back_status_to_processing()
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_PROCESSING
    assert ProgrammationProjet.objects.filter(projet=projet).count() == 0
    simulation_projets = SimulationProjet.objects.filter(projet=projet)
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


@pytest.mark.parametrize(("status"), [Projet.STATUS_PROCESSING])
def test_set_back_status_to_processing_from_other_status_than_accepted_or_refused(
    status,
):
    projet = ProjetFactory(status=status)

    with pytest.raises(TransitionNotAllowed):
        projet.set_back_status_to_processing()


# Dismiss


@pytest.mark.parametrize(
    ("status, montant, taux"),
    ((Projet.STATUS_REFUSED, 0, 0), (Projet.STATUS_ACCEPTED, 10_000, 20)),
)
def test_dismiss(status, montant, taux):
    projet = ProjetFactory(status=status)
    ProgrammationProjetFactory(
        projet=projet,
        status=ProgrammationProjet.STATUS_REFUSED
        if projet.status == Projet.STATUS_REFUSED
        else ProgrammationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory.create_batch(
        3,
        projet=projet,
        status=SimulationProjet.STATUS_REFUSED
        if projet.status == Projet.STATUS_REFUSED
        else ProgrammationProjet.STATUS_ACCEPTED,
        montant=montant,
        taux=taux,
    )

    projet.dismiss()
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_DISMISSED
    assert ProgrammationProjet.objects.filter(projet=projet).count() == 0
    simulation_projets = SimulationProjet.objects.filter(projet=projet)
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


def test_dismiss_from_processing():
    projet = ProjetFactory(status=Projet.STATUS_PROCESSING)
    SimulationProjetFactory.create_batch(
        3,
        projet=projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=500,
        taux=0.4,
    )

    projet.dismiss()
    projet.save()
    projet.refresh_from_db()

    assert projet.status == Projet.STATUS_DISMISSED
    assert ProgrammationProjet.objects.filter(projet=projet).count() == 0
    simulation_projets = SimulationProjet.objects.filter(projet=projet)
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0
