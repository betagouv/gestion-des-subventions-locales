from typing import cast
from unittest import mock

import pytest

from gsl_core.models import Collegue
from gsl_core.tests.factories import CollegueFactory
from gsl_programmation.models import ProgrammationProjet
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
)
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.forms import SimulationProjetStatusForm
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> Collegue:
    return cast(Collegue, CollegueFactory())


@pytest.mark.parametrize(
    ("simulation_projet_status, dotation_projet_transition"),
    (
        (SimulationProjet.STATUS_REFUSED, "refuse"),
        (SimulationProjet.STATUS_DISMISSED, "dismiss"),
    ),
)
def test_refuse_or_dismiss_does_not_touch_ds(
    simulation_projet_status, dotation_projet_transition, user
):
    """
    Refuse and dismiss only update the DotationProjet status: no DS mutation,
    no projet.notified_at update. Notification is now a separate step.
    """
    simulation_projet = SimulationProjetFactory()

    with mock.patch(
        f"gsl_projet.models.DotationProjet.{dotation_projet_transition}",
        wraps=getattr(simulation_projet.dotation_projet, dotation_projet_transition),
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
        assiette=simulation_projet.dotation_projet.assiette,
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
def test_accept_a_simulation_projet_has_created_a_programmation_projet_with_mother_enveloppe(
    mock_ds_update,
    user,
):
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    simulation = SimulationFactory(enveloppe=child_enveloppe)
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING,
        simulation=simulation,
        dotation_projet__dotation=DOTATION_DETR,
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    form = SimulationProjetStatusForm(instance=simulation_projet, status=new_status)
    form.save(user)

    mock_ds_update.assert_called_once_with(
        dossier=simulation_projet.projet.dossier_ds,
        user=user,
        annotations_dotation_to_update=simulation_projet.dotation,
        dotations_to_be_checked=[simulation_projet.dotation],
        assiette=simulation_projet.dotation_projet.assiette,
        montant=simulation_projet.montant,
        taux=simulation_projet.taux,
    )

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        dotation_projet=simulation_projet.dotation_projet
    )
    assert programmation_projets_qs.count() == 1
    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe


@mock.patch(
    "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
)
@pytest.mark.parametrize(
    "initial_programmation_status, new_projet_status, programmation_status_expected",
    (
        (
            ProgrammationProjet.STATUS_REFUSED,
            SimulationProjet.STATUS_ACCEPTED,
            ProgrammationProjet.STATUS_ACCEPTED,
        ),
    ),
)
def test_accept_a_simulation_projet_has_updated_a_programmation_projet_with_mother_enveloppe(
    mock_ds_update,
    initial_programmation_status,
    new_projet_status,
    programmation_status_expected,
    user,
):
    mother_enveloppe = DetrEnveloppeFactory()
    child_enveloppe = DetrEnveloppeFactory(deleguee_by=mother_enveloppe)
    simulation = SimulationFactory(enveloppe=child_enveloppe)
    dotation_projet = DotationProjetFactory(
        projet__dossier_ds__perimetre=child_enveloppe.perimetre, dotation=DOTATION_DETR
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
            assiette=simulation_projet.dotation_projet.assiette,
            montant=simulation_projet.montant,
            taux=simulation_projet.taux,
        )

    programmation_projets_qs = ProgrammationProjet.objects.filter(
        dotation_projet=simulation_projet.dotation_projet
    )
    assert programmation_projets_qs.count() == 1

    programmation_projet = programmation_projets_qs.first()
    assert programmation_projet.enveloppe == mother_enveloppe
    assert programmation_projet.status == programmation_status_expected
