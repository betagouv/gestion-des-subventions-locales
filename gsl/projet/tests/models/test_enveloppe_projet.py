from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError
from django.forms import ValidationError
from django.utils import timezone
from django_fsm import TransitionNotAllowed

from gsl.historique.models import ProjetAction
from gsl.simulation.models import SimulationProjet
from gsl.simulation.tests.factories import SimulationProjetFactory
from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreRegionalFactory,
)
from gsl_demarches_simplifiees.models import Dossier
from gsl_notification.tests.factories import (
    AnnexeFactory,
    ArreteFactory,
    LettreEtArreteSignesFactory,
    LettreNotificationFactory,
    LettreRefusFactory,
    LettreRefusSigneeFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)

from ...constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    DOTATIONS,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from ...models import (
    EnveloppeProjet,
)
from ..factories import (
    EnveloppeProjetFactory,
    ProjetFactory,
)

pytestmark = pytest.mark.django_db


# -- manager --


def test_enveloppe_projet_manager_excludes_inactive_dossier():
    EnveloppeProjetFactory()
    EnveloppeProjetFactory(projet__dossier_ds__is_active=False)

    assert EnveloppeProjet.objects.active().count() == 1


# -- compute_montant_from_taux --


def test_compute_montant_from_taux():
    enveloppe_projet = EnveloppeProjetFactory(
        projet__dossier_ds__finance_cout_total=100_000,
    )
    assert enveloppe_projet.compute_montant_from_taux(25) == 25_000

    enveloppe_projet = EnveloppeProjetFactory(
        assiette=50_000,
    )
    assert enveloppe_projet.compute_montant_from_taux(25) == 12_500

    enveloppe_projet = EnveloppeProjetFactory()
    assert enveloppe_projet.compute_montant_from_taux(25) == 0


@pytest.mark.parametrize(("dotation"), DOTATIONS)
def test_enveloppe_projet_unicity(dotation):
    projet = ProjetFactory()
    EnveloppeProjet(projet=projet, dotation=dotation).save()
    with pytest.raises(IntegrityError):
        EnveloppeProjet(projet=projet, dotation=dotation).save()


def test_dsil_enveloppe_projet_must_have_a_detr_avis_commission_null():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL, detr_avis_commission=True
    )
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.full_clean()

    assert exc_info.value.message_dict["detr_avis_commission"][0] == (
        "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
    )


def test_assiette_or_cout_total():
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=1_000, projet__dossier_ds__finance_cout_total=2_000
    )
    assert enveloppe_projet.assiette_or_cout_total == 1_000

    enveloppe_projet = EnveloppeProjetFactory(
        assiette=None, projet__dossier_ds__finance_cout_total=2_000
    )
    assert enveloppe_projet.assiette_or_cout_total == 2_000


def test_montant_retenu_when_accepted():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_ACCEPTED, montant=10_000
    )
    assert enveloppe_projet.montant_retenu == 10_000


def test_montant_retenu_when_not_programmed():
    enveloppe_projet = EnveloppeProjetFactory(status=PROJET_STATUS_PROCESSING)
    assert enveloppe_projet.montant_retenu is None


def test_montant_retenu_when_refused():
    enveloppe_projet = EnveloppeProjetFactory(status=PROJET_STATUS_REFUSED, montant=0)
    assert enveloppe_projet.montant_retenu == 0


def test_taux_retenu_when_accepted():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_ACCEPTED, montant=100, assiette=1_000
    )
    assert enveloppe_projet.taux_retenu == 10


def test_taux_retenu_when_not_programmed():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_PROCESSING, assiette=1_000
    )
    assert enveloppe_projet.taux_retenu is None


def test_taux_retenu_when_refused():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_REFUSED, montant=0, assiette=1_000
    )
    assert enveloppe_projet.taux_retenu == 0


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (PROJET_STATUS_ACCEPTED, True),
        (PROJET_STATUS_REFUSED, True),
        (PROJET_STATUS_DISMISSED, True),
        (PROJET_STATUS_PROCESSING, False),
    ),
)
def test_is_treated(status, expected):
    enveloppe_projet = EnveloppeProjetFactory(status=status)
    assert enveloppe_projet.is_treated is expected


@pytest.mark.parametrize(
    ("dotation, avis_commission, must_raise_error"),
    (
        (DOTATION_DETR, True, False),
        (DOTATION_DETR, False, False),
        (DOTATION_DSIL, True, True),
        (DOTATION_DSIL, False, True),
    ),
)
def test_error_raised_if_detr_avis_commission_is_set_on_dsil_projet(
    dotation, avis_commission, must_raise_error
):
    enveloppe_projet = EnveloppeProjetFactory(dotation=dotation)
    enveloppe_projet.detr_avis_commission = avis_commission
    exclude = ["assiette"]

    if must_raise_error:
        with pytest.raises(ValidationError) as exc_info:
            enveloppe_projet.clean_fields(exclude=exclude)
        assert (
            str(exc_info.value.messages[0])
            == "L'avis de la commission DETR ne doit être renseigné que pour les projets DETR."
        )
    else:
        enveloppe_projet.clean_fields(exclude=exclude)
        assert enveloppe_projet.detr_avis_commission == avis_commission


@pytest.mark.parametrize(
    ("cout_total, assiette, must_raise_error"),
    (
        (None, 1_000, False),
        (1_000, 1_000, False),
        (1_000, 1_001, True),
    ),
)
def test_error_raised_if_assiette_is_greater_than_cout_total(
    cout_total, assiette, must_raise_error
):
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=assiette,
        projet__dossier_ds__finance_cout_total=cout_total,
    )
    exclude = ["detr_avis_commission"]

    if must_raise_error:
        with pytest.raises(ValidationError) as exc_info:
            enveloppe_projet.clean_fields(exclude=exclude)
        assert (
            str(exc_info.value.messages[0])
            == "L'assiette doit être inférieure ou égale au coût total du projet."
        )
    else:
        enveloppe_projet.clean_fields(exclude=exclude)
        assert enveloppe_projet.assiette == assiette


@pytest.mark.django_db
def test_get_other_accepted_dotations_with_one_processing_dotation():
    detr_dp = EnveloppeProjetFactory(dotation=DOTATION_DETR)

    assert detr_dp.other_accepted_dotations == []

    dsil_dp = EnveloppeProjetFactory(
        projet=detr_dp.projet,
        status=PROJET_STATUS_PROCESSING,
        dotation=DOTATION_DSIL,
    )
    assert detr_dp.other_accepted_dotations == []

    dsil_dp.accept_without_ds_update(montant=1_000, enveloppe=DsilEnveloppeFactory())
    dsil_dp.save()
    assert detr_dp.other_accepted_dotations == [DOTATION_DSIL]


# Accept


def test_accept_enveloppe_projet_without_simulation_projet():
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=10_000, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    assert enveloppe_projet.projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2025)

    # --

    enveloppe_projet.accept_without_ds_update(montant=5_000, enveloppe=enveloppe)
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    # --

    assert enveloppe_projet.status == PROJET_STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        enveloppe_projet=enveloppe_projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    assert simulation_projets.count() == 0

    assert enveloppe_projet.enveloppe == enveloppe
    assert enveloppe_projet.montant == 5_000
    assert enveloppe_projet.taux_retenu == 50


def test_accept_enveloppe_projet():
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=10_000, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    assert enveloppe_projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        montant=1_000,
    )
    SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_REFUSED,
        montant=2_000,
    )
    SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=3_000,
    )
    assert (
        SimulationProjet.objects.filter(enveloppe_projet=enveloppe_projet).count() == 3
    )

    enveloppe = DetrEnveloppeFactory(annee=2025)

    # --

    enveloppe_projet.accept_without_ds_update(montant=5_000, enveloppe=enveloppe)
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    # --

    assert enveloppe_projet.status == PROJET_STATUS_ACCEPTED
    simulation_projets = SimulationProjet.objects.filter(
        enveloppe_projet=enveloppe_projet, status=SimulationProjet.STATUS_ACCEPTED
    )
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_ACCEPTED
        assert simulation_projet.montant == 5_000
        assert simulation_projet.taux == 50

    assert enveloppe_projet.enveloppe == enveloppe
    assert enveloppe_projet.montant == 5_000
    assert enveloppe_projet.taux_retenu == 50


def test_accept_enveloppe_projet_replaces_a_previous_programmation():
    enveloppe = DetrEnveloppeFactory(annee=2025)
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=9_000,
        status=PROJET_STATUS_REFUSED,
        dotation=DOTATION_DETR,
        enveloppe=enveloppe,
        montant=0,
    )

    # --

    enveloppe_projet.accept_without_ds_update(montant=5_000, enveloppe=enveloppe)
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    # --

    assert enveloppe_projet.status == PROJET_STATUS_ACCEPTED
    assert enveloppe_projet.enveloppe == enveloppe
    assert enveloppe_projet.montant == 5_000
    assert round(enveloppe_projet.taux_retenu, 4) == Decimal("55.5556")


def test_accept_enveloppe_projet_select_parent_enveloppe():
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=9_000,
        status=PROJET_STATUS_PROCESSING,
        dotation=DOTATION_DSIL,
    )
    parent_enveloppe = DsilEnveloppeFactory()
    child_enveloppe = DsilEnveloppeFactory(deleguee_by=parent_enveloppe)

    # --

    enveloppe_projet.accept_without_ds_update(montant=5_000, enveloppe=child_enveloppe)

    # --

    assert enveloppe_projet.enveloppe == parent_enveloppe


def test_accept_with_a_dotation_enveloppe_different_from_the_dotation():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
    )
    enveloppe = DsilEnveloppeFactory()
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.accept_without_ds_update(montant=5_000, enveloppe=enveloppe)
    assert (
        str(exc_info.value.message)
        == "La dotation du projet et de l'enveloppe ne correspondent pas."
    )


def test_accept_creates_status_change_action_when_status_was_different():
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=10_000, dotation=DOTATION_DETR, status=PROJET_STATUS_PROCESSING
    )
    enveloppe = DetrEnveloppeFactory(annee=2025)

    enveloppe_projet.accept_without_ds_update(montant=5_000, enveloppe=enveloppe)

    actions = ProjetAction.objects.filter(
        projet=enveloppe_projet.projet,
        action_type=ProjetAction.TYPE_STATUS_CHANGE,
        status=PROJET_STATUS_ACCEPTED,
    )
    assert actions.count() == 1
    assert actions.first().enveloppe == enveloppe


def test_accept_does_not_create_status_change_action_when_already_accepted_and_same_enveloppe():
    enveloppe = DetrEnveloppeFactory(annee=2025)
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=10_000,
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        enveloppe=enveloppe,
    )

    enveloppe_projet.accept_without_ds_update(montant=6_000, enveloppe=enveloppe)

    assert (
        ProjetAction.objects.filter(
            projet=enveloppe_projet.projet,
            action_type=ProjetAction.TYPE_STATUS_CHANGE,
        ).count()
        == 0
    )


def test_accept_creates_status_change_action_when_already_accepted_but_enveloppe_changed():
    old_enveloppe = DetrEnveloppeFactory(annee=2024)
    new_enveloppe = DetrEnveloppeFactory(annee=2025)
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=10_000,
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        enveloppe=old_enveloppe,
    )

    enveloppe_projet.accept_without_ds_update(montant=5_000, enveloppe=new_enveloppe)

    actions = ProjetAction.objects.filter(
        projet=enveloppe_projet.projet,
        action_type=ProjetAction.TYPE_STATUS_CHANGE,
        status=PROJET_STATUS_ACCEPTED,
    )
    assert actions.count() == 1
    assert actions.first().enveloppe == new_enveloppe


# Refuse


def test_refusing_a_enveloppe_projet_programmes_it():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_PROCESSING, dotation=DOTATION_DETR
    )
    assert enveloppe_projet.status == PROJET_STATUS_PROCESSING
    assert enveloppe_projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2024)

    enveloppe_projet.refuse(enveloppe=enveloppe)
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    assert enveloppe_projet.status == PROJET_STATUS_REFUSED

    assert enveloppe_projet.enveloppe == enveloppe
    assert enveloppe_projet.montant == 0
    assert enveloppe_projet.taux_retenu == 0


def test_refusing_a_projet_updates_all_simulation_projet():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_PROCESSING, dotation=DOTATION_DETR
    )
    assert enveloppe_projet.status == PROJET_STATUS_PROCESSING
    assert enveloppe_projet.dossier_ds.ds_state == Dossier.STATE_EN_INSTRUCTION

    enveloppe = DetrEnveloppeFactory(annee=2024)

    SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        montant=1_000,
    )
    SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=2_000,
    )
    SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=5_000,
    )
    assert (
        SimulationProjet.objects.filter(enveloppe_projet=enveloppe_projet).count() == 3
    )

    enveloppe_projet.refuse(enveloppe=enveloppe)
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    assert (
        SimulationProjet.objects.filter(enveloppe_projet=enveloppe_projet).count() == 3
    )
    simulation_projets = SimulationProjet.objects.filter(
        enveloppe_projet=enveloppe_projet
    )
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_REFUSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


def test_refuse_with_an_dotation_enveloppe_different_from_the_dotation():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
    )
    enveloppe = DsilEnveloppeFactory()
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.refuse(enveloppe=enveloppe)
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
    enveloppe = DetrEnveloppeFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        status=status, dotation=DOTATION_DETR, enveloppe=enveloppe
    )

    simulation_projet_status = (
        SimulationProjet.STATUS_REFUSED
        if enveloppe_projet.status == PROJET_STATUS_REFUSED
        else SimulationProjet.STATUS_ACCEPTED
    )

    SimulationProjetFactory.create_batch(
        3,
        enveloppe_projet=enveloppe_projet,
        status=simulation_projet_status,
        montant=montant,
    )

    enveloppe_projet.dismiss(enveloppe=enveloppe)
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    assert enveloppe_projet.status == PROJET_STATUS_DISMISSED
    assert enveloppe_projet.is_programmee
    simulation_projets = SimulationProjet.objects.filter(
        enveloppe_projet=enveloppe_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


def test_dismiss_from_processing():
    enveloppe = DetrEnveloppeFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_PROCESSING, dotation=DOTATION_DETR
    )
    SimulationProjetFactory.create_batch(
        3,
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=500,
    )

    enveloppe_projet.dismiss(enveloppe=enveloppe)
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    assert enveloppe_projet.status == PROJET_STATUS_DISMISSED
    assert enveloppe_projet.is_programmee
    simulation_projets = SimulationProjet.objects.filter(
        enveloppe_projet=enveloppe_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_DISMISSED
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0


# Set back status to processing


def test_set_back_status_to_processing_without_ds_from_accepted():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_ACCEPTED,
        assiette=50_000,
        montant=10_000,
        projet__notified_at=timezone.now(),
    )
    SimulationProjetFactory.create_batch(
        3,
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_ACCEPTED,
        montant=10_000,
    )

    assert enveloppe_projet.projet.notified_at is not None

    # --
    enveloppe_projet.set_back_status_to_processing_without_ds()
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    # --

    assert enveloppe_projet.status == PROJET_STATUS_PROCESSING
    assert not enveloppe_projet.is_programmee
    simulation_projets = SimulationProjet.objects.filter(
        enveloppe_projet=enveloppe_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert simulation_projet.montant == 10_000
        assert simulation_projet.taux == 20
    assert enveloppe_projet.projet.notified_at is None


@pytest.mark.parametrize(
    ("projet_status, simulation_projet_status"),
    [
        (PROJET_STATUS_REFUSED, SimulationProjet.STATUS_REFUSED),
        (PROJET_STATUS_DISMISSED, SimulationProjet.STATUS_DISMISSED),
    ],
)
def test_set_back_status_to_processing_without_ds_from_refused_or_dismissed(
    projet_status, simulation_projet_status
):
    enveloppe_projet = EnveloppeProjetFactory(
        status=projet_status, projet__notified_at=timezone.now()
    )
    SimulationProjetFactory.create_batch(
        3,
        enveloppe_projet=enveloppe_projet,
        status=simulation_projet_status,
        montant=0,
    )

    assert enveloppe_projet.projet.notified_at is not None

    # --

    enveloppe_projet.set_back_status_to_processing_without_ds()
    enveloppe_projet.save()
    enveloppe_projet.refresh_from_db()

    # --

    assert enveloppe_projet.status == PROJET_STATUS_PROCESSING
    assert not enveloppe_projet.is_programmee
    simulation_projets = SimulationProjet.objects.filter(
        enveloppe_projet=enveloppe_projet
    )
    assert simulation_projets.count() == 3
    for simulation_projet in simulation_projets:
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        assert simulation_projet.montant == 0
        assert simulation_projet.taux == 0
    assert enveloppe_projet.projet.notified_at is None


@pytest.mark.parametrize(("status"), [PROJET_STATUS_PROCESSING])
def test_set_back_status_to_processing_without_ds_from_other_status_than_accepted_or_refused(
    status,
):
    enveloppe_projet = EnveloppeProjetFactory(status=status)

    with pytest.raises(TransitionNotAllowed):
        enveloppe_projet.set_back_status_to_processing_without_ds()


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_set_back_status_to_processing_updates_ds_annotations(mock_update_ds):
    projet = ProjetFactory()
    user = CollegueFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    other_dotation = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DSIL, status=PROJET_STATUS_ACCEPTED
    )

    enveloppe_projet.set_back_status_to_processing(user=user)
    enveloppe_projet.save()

    mock_update_ds.assert_called_once_with(
        dossier=enveloppe_projet.projet.dossier_ds,
        user=user,
        dotations_to_be_checked=[other_dotation.dotation],
    )


@mock.patch("gsl_demarches_simplifiees.services.DsService.repasser_en_instruction")
@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_set_back_status_to_processing_calls_repasser_en_instruction_when_notified(
    _mock_update_ds, mock_repasser_en_instruction
):
    projet = ProjetFactory(notified_at=timezone.now())
    user = CollegueFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )

    enveloppe_projet.set_back_status_to_processing(user=user)
    enveloppe_projet.save()

    mock_repasser_en_instruction.assert_called_once_with(
        enveloppe_projet.projet.dossier_ds, user
    )


@mock.patch("gsl_demarches_simplifiees.services.DsService.repasser_en_instruction")
@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_set_back_status_to_processing_does_not_call_repasser_en_instruction_when_not_notified(
    _mock_update_ds, mock_repasser_en_instruction
):
    projet = ProjetFactory(notified_at=None)
    user = CollegueFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        projet=projet, dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )

    enveloppe_projet.set_back_status_to_processing(user=user)
    enveloppe_projet.save()

    mock_repasser_en_instruction.assert_not_called()


# -- save() default assiette --


def test_enveloppe_projet_assiette_defaults_to_finance_cout_total_when_no_annotation():
    dp = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=None,
        projet__dossier_ds__finance_cout_total=50_000,
        projet__dossier_ds__annotations_assiette_detr=None,
    )
    assert dp.assiette == 50_000


def test_enveloppe_projet_assiette_uses_detr_annotation_when_set():
    dp = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=None,
        projet__dossier_ds__finance_cout_total=50_000,
        projet__dossier_ds__annotations_assiette_detr=30_000,
    )
    assert dp.assiette == 30_000


def test_enveloppe_projet_assiette_uses_dsil_annotation_when_set():
    dp = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        assiette=None,
        projet__dossier_ds__finance_cout_total=50_000,
        projet__dossier_ds__annotations_assiette_dsil=20_000,
    )
    assert dp.assiette == 20_000


def test_enveloppe_projet_assiette_explicit_value_kept():
    dp = EnveloppeProjetFactory(
        assiette=30_000,
        projet__dossier_ds__finance_cout_total=50_000,
    )
    assert dp.assiette == 30_000


def test_enveloppe_projet_assiette_stays_none_when_no_cout_total_and_no_annotation():
    dp = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=None,
        projet__dossier_ds__finance_cout_total=None,
        projet__dossier_ds__annotations_assiette_detr=None,
    )
    assert dp.assiette is None


def test_enveloppe_projet_save_update_does_not_reset_assiette():
    dp = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        assiette=None,
        projet__dossier_ds__finance_cout_total=50_000,
        projet__dossier_ds__annotations_assiette_detr=None,
    )
    assert dp.assiette == 50_000

    dp.assiette = None
    dp.save()
    dp.refresh_from_db()
    assert dp.assiette is None


# -- documents_summary --


def test_documents_summary_no_document():
    assert EnveloppeProjetFactory().documents_summary == []


def test_documents_summary_arrete_genere():
    enveloppe_projet = EnveloppeProjetFactory(status=PROJET_STATUS_ACCEPTED)
    ArreteFactory(enveloppe_projet=enveloppe_projet)
    LettreNotificationFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.documents_summary == ["1 arrêté", "1 lettre"]


@pytest.mark.parametrize(
    "annexes_count, expected_summary", ((0, []), (1, ["1 annexe"]), (2, ["2 annexes"]))
)
def test_documents_summary_annexes(annexes_count, expected_summary):
    enveloppe_projet = EnveloppeProjetFactory(status=PROJET_STATUS_ACCEPTED)
    AnnexeFactory.create_batch(annexes_count, enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.documents_summary == expected_summary


def test_documents_summary_lettre_et_arrete_signes_hides_arrete_and_lettre_generes():
    enveloppe_projet = EnveloppeProjetFactory(status=PROJET_STATUS_ACCEPTED)
    LettreEtArreteSignesFactory(enveloppe_projet=enveloppe_projet)
    ArreteFactory(enveloppe_projet=enveloppe_projet)
    LettreNotificationFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.documents_summary == ["1 lettre et arrêté signés"]


def test_documents_summary_lettre_refus_generee():
    enveloppe_projet = EnveloppeProjetFactory(status=PROJET_STATUS_REFUSED)
    LettreRefusFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.documents_summary == ["1 lettre de refus"]


def test_documents_summary_lettre_refus_signee_hides_lettre_refus_generee():
    enveloppe_projet = EnveloppeProjetFactory(status=PROJET_STATUS_REFUSED)
    LettreRefusSigneeFactory(enveloppe_projet=enveloppe_projet)
    LettreRefusFactory(enveloppe_projet=enveloppe_projet)

    assert enveloppe_projet.documents_summary == ["1 lettre de refus signée"]


# -- programmation --


@pytest.mark.parametrize(
    "montant, assiette, finance_cout_total, expected_taux",
    (
        (1_000, 2_000, 4_000, 50),
        (1_000, 2_000, None, 50),
        (1_000, None, 4_000, 25),
        (1_000, None, None, 0),
    ),
)
def test_taux_retenu_falls_back_on_cout_total(
    montant, assiette, finance_cout_total, expected_taux
):
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_ACCEPTED,
        montant=montant,
        assiette=assiette,
        projet__dossier_ds__finance_cout_total=finance_cout_total,
    )
    assert isinstance(enveloppe_projet.taux_retenu, Decimal)
    assert enveloppe_projet.taux_retenu == expected_taux


def test_montant_cant_be_higher_than_assiette():
    enveloppe_projet = EnveloppeProjetFactory(
        assiette=100,
        projet__dossier_ds__finance_cout_total=200,
        status=PROJET_STATUS_ACCEPTED,
        montant=101,
    )
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.clean()
    assert (
        "Le montant de la programmation ne peut pas être supérieur à l'assiette du projet pour cette dotation."
        in exc_info.value.message_dict["montant"][0]
    )


def test_a_projet_can_be_accepted_on_two_different_enveloppes():
    detr_dotation = EnveloppeProjetFactory(
        dotation=DOTATION_DETR, status=PROJET_STATUS_ACCEPTED
    )
    EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        projet=detr_dotation.projet,
        status=PROJET_STATUS_ACCEPTED,
        enveloppe=DsilEnveloppeFactory(annee=detr_dotation.enveloppe.annee),
    )


def test_clean_rejects_a_deleguee_enveloppe():
    perimetre = PerimetreArrondissementFactory()
    mother = DsilEnveloppeFactory(
        perimetre=PerimetreRegionalFactory(region=perimetre.region)
    )
    enveloppe_projet = EnveloppeProjetFactory(
        projet__dossier_ds__perimetre=perimetre,
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_ACCEPTED,
        montant=Decimal("100.00"),
        assiette=Decimal("1234.00"),
        enveloppe=DsilEnveloppeFactory(deleguee_by=mother, perimetre=perimetre),
    )
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.clean()
    assert (
        "Une programmation ne peut pas être faite sur une enveloppe déléguée."
        in exc_info.value.message_dict["enveloppe"][0]
    )


def test_clean_accepts_a_coherent_programmation():
    perimetre = PerimetreArrondissementFactory()
    enveloppe_projet = EnveloppeProjetFactory(
        projet__dossier_ds__perimetre=perimetre,
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_ACCEPTED,
        montant=Decimal("100.00"),
        assiette=Decimal("1234.00"),
        enveloppe=DsilEnveloppeFactory(
            perimetre=PerimetreRegionalFactory(region=perimetre.region)
        ),
    )
    enveloppe_projet.clean()


def test_clean_rejects_a_refused_dotation_with_a_montant():
    enveloppe_projet = EnveloppeProjetFactory(
        status=PROJET_STATUS_REFUSED, assiette=Decimal("1234.00")
    )
    enveloppe_projet.montant = Decimal("100.00")
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.clean()
    assert (
        "Un projet refusé doit avoir un montant nul."
        in exc_info.value.message_dict["montant"][0]
    )


def test_clean_rejects_an_enveloppe_outside_the_projet_perimetre():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_ACCEPTED,
        enveloppe=DsilEnveloppeFactory(),
    )
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.clean()
    assert (
        "Le périmètre de l'enveloppe ne contient pas le périmètre du projet."
        in exc_info.value.message_dict["enveloppe"][0]
    )


def test_clean_rejects_an_enveloppe_of_another_dotation():
    enveloppe_projet = EnveloppeProjetFactory(
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_ACCEPTED,
        enveloppe=DsilEnveloppeFactory(),
    )
    with pytest.raises(ValidationError) as exc_info:
        enveloppe_projet.clean()
    assert (
        "La dotation de l'enveloppe ne correspond pas à celle du projet pour cette dotation."
        in exc_info.value.message_dict["enveloppe"][0]
    )


def test_to_notify():
    accepted_not_notified = EnveloppeProjetFactory(
        status=PROJET_STATUS_ACCEPTED, projet__notified_at=None
    )
    EnveloppeProjetFactory(
        status=PROJET_STATUS_ACCEPTED, projet__notified_at=timezone.now()
    )
    refused_not_notified = EnveloppeProjetFactory(
        status=PROJET_STATUS_REFUSED, projet__notified_at=None
    )
    EnveloppeProjetFactory(
        status=PROJET_STATUS_REFUSED, projet__notified_at=timezone.now()
    )

    result = EnveloppeProjet.objects.to_notify()

    assert accepted_not_notified in result
    assert refused_not_notified in result
    assert result.count() == 2
