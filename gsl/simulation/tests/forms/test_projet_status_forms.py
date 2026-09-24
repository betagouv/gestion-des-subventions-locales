from typing import cast
from unittest import mock

import pytest

from gsl.projet.constants import (
    DOTATION_DETR,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl.projet.tests.factories import EnveloppeProjetFactory
from gsl_core.models import Collegue
from gsl_core.tests.factories import CollegueFactory
from gsl_programmation.tests.factories import DetrEnveloppeFactory

from ...forms import SimulationProjetStatusForm
from ...models import SimulationProjet
from ..factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> Collegue:
    return cast(Collegue, CollegueFactory())


@pytest.mark.parametrize(
    ("simulation_projet_status, enveloppe_projet_transition"),
    (
        (SimulationProjet.STATUS_REFUSED, "refuse"),
        (SimulationProjet.STATUS_DISMISSED, "dismiss"),
    ),
)
def test_refuse_or_dismiss_does_not_touch_ds(
    simulation_projet_status, enveloppe_projet_transition, user
):
    """
    Refuse and dismiss only update the EnveloppeProjet status: no DS mutation,
    no projet.notified_at update. Notification is now a separate step.
    """
    simulation_projet = SimulationProjetFactory()

    with mock.patch(
        f"gsl.projet.models.EnveloppeProjet.{enveloppe_projet_transition}",
        wraps=getattr(simulation_projet.enveloppe_projet, enveloppe_projet_transition),
    ) as mock_transition:
        with (
            mock.patch(
                "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_refuser"
            ) as mock_refuser,
            mock.patch(
                "gsl_demarches_simplifiees.services.DsService.dismiss_in_ds"
            ) as mock_dismiss,
        ):
            form = SimulationProjetStatusForm(
                instance=simulation_projet, status=simulation_projet_status
            )
            form.save(user)

    mock_transition.assert_called_once_with(
        enveloppe=simulation_projet.enveloppe, actor=user
    )
    mock_refuser.assert_not_called()
    mock_dismiss.assert_not_called()

    simulation_projet.refresh_from_db()
    assert simulation_projet.projet.notified_at is None


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_update_status_with_accepted(mock_ds_update, user):
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    form = SimulationProjetStatusForm(instance=simulation_projet, status=new_status)
    form.save(user)

    mock_ds_update.assert_called_once_with(
        dossier=simulation_projet.projet.dossier_ds,
        user=user,
        annotations_dotation_to_update=simulation_projet.dotation,
        dotations_to_be_checked=[simulation_projet.dotation],
        assiette=simulation_projet.enveloppe_projet.assiette,
        montant=simulation_projet.montant,
        taux=simulation_projet.taux,
    )


def test_update_status_with_processing(user):
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    )
    new_status = SimulationProjet.STATUS_PROCESSING

    form = SimulationProjetStatusForm(instance=simulation_projet, status=new_status)
    form.save(user)

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == new_status


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
def test_accept_a_simulation_projet_programmes_it_on_the_mother_enveloppe(
    mock_ds_update,
    user,
):
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(parent=mother_enveloppe)
    simulation = SimulationFactory(enveloppe=child_enveloppe)
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING,
        simulation=simulation,
        enveloppe_projet__dotation=DOTATION_DETR,
        enveloppe_projet__status=PROJET_STATUS_PROCESSING,
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    form = SimulationProjetStatusForm(instance=simulation_projet, status=new_status)
    form.save(user)

    mock_ds_update.assert_called_once_with(
        dossier=simulation_projet.projet.dossier_ds,
        user=user,
        annotations_dotation_to_update=simulation_projet.dotation,
        dotations_to_be_checked=[simulation_projet.dotation],
        assiette=simulation_projet.enveloppe_projet.assiette,
        montant=simulation_projet.montant,
        taux=simulation_projet.taux,
    )

    simulation_projet.enveloppe_projet.refresh_from_db()
    assert simulation_projet.enveloppe_projet.enveloppe == mother_enveloppe


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize(
    "initial_programmation_status, new_projet_status, programmation_status_expected",
    (
        (
            PROJET_STATUS_REFUSED,
            SimulationProjet.STATUS_ACCEPTED,
            PROJET_STATUS_ACCEPTED,
        ),
    ),
)
def test_accept_a_simulation_projet_reprogrammes_it_on_the_mother_enveloppe(
    mock_ds_update,
    initial_programmation_status,
    new_projet_status,
    programmation_status_expected,
    user,
):
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(parent=mother_enveloppe)
    simulation = SimulationFactory(enveloppe=child_enveloppe)
    enveloppe_projet = EnveloppeProjetFactory(
        projet__dossier_ds__perimetre=child_enveloppe.perimetre,
        dotation=DOTATION_DETR,
        status=initial_programmation_status,
        enveloppe=mother_enveloppe,
    )

    simulation_projet = SimulationProjetFactory(
        enveloppe_projet=enveloppe_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        simulation=simulation,
    )

    form = SimulationProjetStatusForm(
        instance=simulation_projet, status=new_projet_status
    )
    form.save(user)

    if new_projet_status == SimulationProjet.STATUS_ACCEPTED:
        mock_ds_update.assert_called_once_with(
            dossier=simulation_projet.projet.dossier_ds,
            user=user,
            annotations_dotation_to_update=simulation_projet.dotation,
            dotations_to_be_checked=[simulation_projet.dotation],
            assiette=simulation_projet.enveloppe_projet.assiette,
            montant=simulation_projet.montant,
            taux=simulation_projet.taux,
        )

    enveloppe_projet.refresh_from_db()
    assert enveloppe_projet.enveloppe == mother_enveloppe
    assert enveloppe_projet.status == programmation_status_expected


# ---------------------------------------------------------------------------
# Revert to processing from a final status (new elif branch in save())
# ---------------------------------------------------------------------------


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize(
    "initial_simulation_status, initial_dotation_status",
    (
        (SimulationProjet.STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED),
        (SimulationProjet.STATUS_REFUSED, PROJET_STATUS_REFUSED),
        (SimulationProjet.STATUS_DISMISSED, PROJET_STATUS_DISMISSED),
    ),
)
def test_revert_from_final_status_resets_enveloppe_projet_to_processing(
    mock_ds_update,
    initial_simulation_status,
    initial_dotation_status,
    user,
):
    simulation_projet = SimulationProjetFactory(
        status=initial_simulation_status,
        enveloppe_projet__status=initial_dotation_status,
    )
    form = SimulationProjetStatusForm(
        instance=simulation_projet, status=SimulationProjet.STATUS_PROCESSING
    )
    form.save(user)

    simulation_projet.enveloppe_projet.refresh_from_db()
    assert simulation_projet.enveloppe_projet.status == PROJET_STATUS_PROCESSING


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize(
    "initial_simulation_status, initial_dotation_status",
    (
        (SimulationProjet.STATUS_ACCEPTED, PROJET_STATUS_ACCEPTED),
        (SimulationProjet.STATUS_REFUSED, PROJET_STATUS_REFUSED),
        (SimulationProjet.STATUS_DISMISSED, PROJET_STATUS_DISMISSED),
    ),
)
def test_revert_from_final_status_drops_the_programmation(
    mock_ds_update,
    initial_simulation_status,
    initial_dotation_status,
    user,
):
    simulation_projet = SimulationProjetFactory(
        status=initial_simulation_status,
        enveloppe_projet__status=initial_dotation_status,
    )
    form = SimulationProjetStatusForm(
        instance=simulation_projet, status=SimulationProjet.STATUS_PROCESSING
    )
    form.save(user)

    simulation_projet.enveloppe_projet.refresh_from_db()
    assert not simulation_projet.enveloppe_projet.is_programmee


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize(
    "initial_status, new_status",
    (
        (
            SimulationProjet.STATUS_PROCESSING,
            SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        ),
        (
            SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
            SimulationProjet.STATUS_PROCESSING,
        ),
        (
            SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
            SimulationProjet.STATUS_PROCESSING,
        ),
    ),
)
def test_pending_to_pending_does_not_revert_enveloppe_projet(
    mock_ds_update,
    initial_status,
    new_status,
    user,
):
    simulation_projet = SimulationProjetFactory(
        status=initial_status,
        enveloppe_projet__status=PROJET_STATUS_PROCESSING,
    )
    form = SimulationProjetStatusForm(instance=simulation_projet, status=new_status)
    form.save(user)

    simulation_projet.enveloppe_projet.refresh_from_db()
    assert simulation_projet.enveloppe_projet.status == PROJET_STATUS_PROCESSING
