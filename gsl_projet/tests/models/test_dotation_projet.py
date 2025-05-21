from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.forms import ValidationError
from django_fsm import TransitionNotAllowed

from gsl_demarches_simplifiees.models import Dossier
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.models import DotationProjet
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(("dotation"), DOTATIONS)
def test_dotation_projet_unicity(dotation):
    projet = ProjetFactory()
    DotationProjet(projet=projet, dotation=dotation).save()
    with pytest.raises(IntegrityError):
        DotationProjet(projet=projet, dotation=dotation).save()


def test_dsil_dotation_projet_must_have_a_detr_avis_commission_null():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DSIL, detr_avis_commission=True
    )
    with pytest.raises(ValidationError) as exc_info:
        dotation_projet.full_clean()

    assert exc_info.value.message_dict["detr_avis_commission"][0] == (
        "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
    )


def test_assiette_or_cout_total():
    dotation_projet = DotationProjetFactory(
        assiette=1_000, projet__dossier_ds__finance_cout_total=2_000
    )
    assert dotation_projet.assiette_or_cout_total == 1_000

    dotation_projet = DotationProjetFactory(
        assiette=None, projet__dossier_ds__finance_cout_total=2_000
    )
    assert dotation_projet.assiette_or_cout_total == 2_000


def test_montant_retenu_with_accepted_programmation_projet():
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED, montant=10_000
    )
    assert programmation_projet.dotation_projet.montant_retenu == 10_000


def test_montant_retenu_with_refused_programmation_projet():
    dotation_projet = DotationProjetFactory()
    assert dotation_projet.montant_retenu is None

    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_REFUSED,
        montant=0,
    )
    assert dotation_projet.montant_retenu == 0


def test_taux_retenu_with_accepted_programmation_projet():
    programmation_projet = ProgrammationProjetFactory(
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=100,
        dotation_projet__assiette=1_000,
    )
    assert programmation_projet.dotation_projet.taux_retenu == 10


def test_taux_retenu_with_refused_programmation_projet():
    dotation_projet = DotationProjetFactory(assiette=1_000)
    assert dotation_projet.taux_retenu is None

    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_REFUSED,
        montant=0,
    )
    assert dotation_projet.taux_retenu == 0


@pytest.mark.parametrize(
    ("dotation, avis_commission, must_raise_error"),
    (
        (DOTATION_DETR, True, False),
        (DOTATION_DETR, False, False),
        (DOTATION_DETR, None, False),
        (DOTATION_DSIL, True, True),
        (DOTATION_DSIL, False, True),
        (DOTATION_DSIL, None, False),
    ),
)
def test_error_raised_if_detr_avis_commission_is_set_on_dsil_projet(
    dotation, avis_commission, must_raise_error
):
    dotation_projet = DotationProjetFactory(dotation=dotation)
    dotation_projet.detr_avis_commission = avis_commission

    if must_raise_error:
        with pytest.raises(ValidationError) as exc_info:
            dotation_projet.clean()
        assert (
            str(exc_info.value.messages[0])
            == "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
        )
    else:
        dotation_projet.clean()
        assert dotation_projet.detr_avis_commission == avis_commission


@pytest.mark.parametrize(
    ("cout_total, assiette, must_raise_error"),
    (
        (None, 1_000, False),
        (1_000, 1_000, False),
        (1_000, 1_001, True),
        (1_000, None, False),
    ),
)
def test_error_raised_if_assiette_is_greater_than_cout_total(
    cout_total, assiette, must_raise_error
):
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        assiette=assiette,
        projet__dossier_ds__finance_cout_total=cout_total,
    )

    if must_raise_error:
        with pytest.raises(ValidationError) as exc_info:
            dotation_projet.clean()
        assert (
            str(exc_info.value.messages[0])
            == "L'assiette ne doit pas être supérieure au coût total du projet."
        )
    else:
        dotation_projet.clean()
        assert dotation_projet.assiette == assiette


# Accept


def test_accept_dotation_projet_without_simulation_projet():
    dotation_projet = DotationProjetFactory(assiette=10_000, dotation=DOTATION_DETR)
    assert dotation_projet.projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2025)

    dotation_projet.accept(montant=5_000, enveloppe=enveloppe)
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == PROJET_STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    assert simulation_projets.count() == 0

    programmation_projets = ProgrammationProjet.objects.filter(
        dotation_projet=dotation_projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 50
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


def test_accept_dotation_projet():
    dotation_projet = DotationProjetFactory(assiette=10_000, dotation=DOTATION_DETR)
    assert dotation_projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        montant=1_000,
    )
    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_REFUSED,
        montant=2_000,
    )
    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=3_000,
    )
    assert SimulationProjet.objects.filter(dotation_projet=dotation_projet).count() == 3

    enveloppe = DetrEnveloppeFactory(annee=2025)

    dotation_projet.accept(montant=5_000, enveloppe=enveloppe)
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == PROJET_STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 5_000
        assert simulation_projet.taux == 50

    programmation_projets = ProgrammationProjet.objects.filter(
        dotation_projet=dotation_projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == 50
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


def test_accept_dotation_projet_update_programmation_projet():
    dotation_projet = DotationProjetFactory(
        assiette=9_000, status=PROJET_STATUS_REFUSED, dotation=DOTATION_DETR
    )

    enveloppe = DetrEnveloppeFactory(annee=2025)
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        enveloppe=enveloppe,
        montant=0,
        status=ProgrammationProjet.STATUS_REFUSED,
    )

    dotation_projet.accept(montant=5_000, enveloppe=enveloppe)
    dotation_projet.save()
    dotation_projet.refresh_from_db()
    assert dotation_projet.status == PROJET_STATUS_ACCEPTED

    programmation_projets = ProgrammationProjet.objects.filter(
        dotation_projet=dotation_projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 5_000
    assert programmation_projet.taux == Decimal("55.56")
    assert programmation_projet.status == ProgrammationProjet.STATUS_ACCEPTED


def test_accept_dotation_projet_select_parent_enveloppe():
    dotation_projet = DotationProjetFactory(
        assiette=9_000,
        status=PROJET_STATUS_PROCESSING,
        dotation=DOTATION_DSIL,
    )
    parent_enveloppe = DsilEnveloppeFactory()
    child_enveloppe = DsilEnveloppeFactory(deleguee_by=parent_enveloppe)
    dotation_projet.accept(montant=5_000, enveloppe=child_enveloppe)

    programmation_projets = ProgrammationProjet.objects.filter(
        dotation_projet=dotation_projet
    )

    assert programmation_projets.count() == 1
    assert programmation_projets.first().enveloppe == parent_enveloppe


def test_accept_with_a_dotation_enveloppe_different_from_the_dotation():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
    )
    enveloppe = DsilEnveloppeFactory()
    with pytest.raises(ValidationError) as exc_info:
        dotation_projet.accept(montant=5_000, enveloppe=enveloppe)
    assert (
        str(exc_info.value.message)
        == "La dotation du projet et de l'enveloppe ne correspondent pas."
    )


# Refuse


def test_refusing_a_dotation_projet_creates_one_programmation_projet():
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING, dotation=DOTATION_DETR
    )
    assert dotation_projet.status == PROJET_STATUS_PROCESSING
    assert dotation_projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2024)

    dotation_projet.refuse(enveloppe=enveloppe)
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == PROJET_STATUS_REFUSED

    programmation_projets = ProgrammationProjet.objects.filter(
        dotation_projet=dotation_projet, enveloppe=enveloppe
    )
    assert programmation_projets.count() == 1
    programmation_projet = programmation_projets.first()
    assert programmation_projet.montant == 0
    assert programmation_projet.taux == 0
    assert programmation_projet.status == ProgrammationProjet.STATUS_REFUSED


def test_refusing_a_projet_updates_all_simulation_projet():
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING, dotation=DOTATION_DETR
    )
    assert dotation_projet.status == PROJET_STATUS_PROCESSING
    assert dotation_projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2024)

    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        montant=1_000,
    )
    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=2_000,
    )
    SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=5_000,
    )
    assert SimulationProjet.objects.filter(dotation_projet=dotation_projet).count() == 3

    dotation_projet.refuse(enveloppe=enveloppe)
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert SimulationProjet.objects.filter(dotation_projet=dotation_projet).count() == 3
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet
    )
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


def test_refuse_with_an_dotation_enveloppe_different_from_the_dotation():
    dotation_projet = DotationProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
    )
    enveloppe = DsilEnveloppeFactory()
    with pytest.raises(ValidationError) as exc_info:
        dotation_projet.refuse(enveloppe=enveloppe)
    assert (
        str(exc_info.value.message)
        == "La dotation du projet et de l'enveloppe ne correspondent pas."
    )


# Dismiss


@pytest.mark.parametrize(
    ("status, montant"),
    (
        (PROJET_STATUS_REFUSED, 0),
        (PROJET_STATUS_ACCEPTED, 10_000),
    ),
)
def test_dismiss(status, montant):
    dotation_projet = DotationProjetFactory(status=status, dotation=DOTATION_DETR)
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_REFUSED
        if dotation_projet.status == PROJET_STATUS_REFUSED
        else ProgrammationProjet.STATUS_ACCEPTED,
    )

    simulation_projet_status = (
        SimulationProjet.STATUS_REFUSED
        if dotation_projet.status == PROJET_STATUS_REFUSED
        else ProgrammationProjet.STATUS_ACCEPTED
    )

    SimulationProjetFactory.create_batch(
        3,
        dotation_projet=dotation_projet,
        status=simulation_projet_status,
        montant=montant,
    )

    dotation_projet.dismiss()
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == PROJET_STATUS_DISMISSED
    assert (
        ProgrammationProjet.objects.filter(dotation_projet=dotation_projet).count() == 0
    )
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


def test_dismiss_from_processing():
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING, dotation=DOTATION_DETR
    )
    SimulationProjetFactory.create_batch(
        3,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=500,
    )

    dotation_projet.dismiss()
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == PROJET_STATUS_DISMISSED
    assert (
        ProgrammationProjet.objects.filter(dotation_projet=dotation_projet).count() == 0
    )
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


# Set back status to processing


def test_set_back_status_to_processing_from_accepted():
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_ACCEPTED, assiette=50_000
    )
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_ACCEPTED,
        montant=10_000,
    )
    SimulationProjetFactory.create_batch(
        3,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=10_000,
    )

    dotation_projet.set_back_status_to_processing()
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == PROJET_STATUS_PROCESSING
    assert (
        ProgrammationProjet.objects.filter(dotation_projet=dotation_projet).count() == 0
    )
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert simulation_projet.montant == 10_000
        assert simulation_projet.taux == 20


def test_set_back_status_to_processing_from_refused():
    dotation_projet = DotationProjetFactory(status=PROJET_STATUS_REFUSED)
    ProgrammationProjetFactory(
        dotation_projet=dotation_projet,
        status=ProgrammationProjet.STATUS_REFUSED,
    )
    SimulationProjetFactory.create_batch(
        3,
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_REFUSED,
        montant=0,
    )

    dotation_projet.set_back_status_to_processing()
    dotation_projet.save()
    dotation_projet.refresh_from_db()

    assert dotation_projet.status == PROJET_STATUS_PROCESSING
    assert (
        ProgrammationProjet.objects.filter(dotation_projet=dotation_projet).count() == 0
    )
    simulation_projets = SimulationProjet.objects.filter(
        dotation_projet=dotation_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


@pytest.mark.parametrize(("status"), [PROJET_STATUS_PROCESSING])
def test_set_back_status_to_processing_from_other_status_than_accepted_or_refused(
    status,
):
    dotation_projet = DotationProjetFactory(status=status)

    with pytest.raises(TransitionNotAllowed):
        dotation_projet.set_back_status_to_processing()
