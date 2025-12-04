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
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.forms import (
    DismissProjetForm,
    RefuseProjetForm,
    SimulationProjetStatusForm,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> Collegue:
    return cast(Collegue, CollegueFactory())


@pytest.mark.parametrize(
    ("ds_service, dotation_projet_transition, form_class"),
    (
        (
            ("gsl_simulation.forms.DsMutator.dossier_refuser", False, True),
            (SimulationProjet.STATUS_REFUSED, "refuse", True, False),
            RefuseProjetForm,
        ),
        (
            ("gsl_simulation.forms.DsService.dismiss_in_ds", True, False),
            (SimulationProjet.STATUS_DISMISSED, "dismiss", True, False),
            DismissProjetForm,
        ),
    ),
)
def test_simulation_projet_transition_are_called(
    ds_service,
    dotation_projet_transition,
    form_class,
):
    simulation_projet = SimulationProjetFactory()
    (ds_service, with_user, with_document) = ds_service
    (
        simulation_projet_status,
        dotation_projet_transition,
        with_enveloppe,
        with_montant,
    ) = dotation_projet_transition
    with mock.patch(
        f"gsl_projet.models.DotationProjet.{dotation_projet_transition}",
        wraps=getattr(simulation_projet.dotation_projet, dotation_projet_transition),
    ) as mock_transition_dotation_projet:
        with mock.patch(ds_service) as mock_ds_service:
            args = {}
            kwargs = {}
            if with_enveloppe:
                args["enveloppe"] = simulation_projet.enveloppe
            if with_montant:
                args["montant"] = simulation_projet.montant

            form = form_class(
                data={"justification": "justification"}, instance=simulation_projet
            )
            form.is_valid()
            user = CollegueFactory()
            form.save(simulation_projet_status, user)
            mock_transition_dotation_projet.assert_called_once_with(**args, **kwargs)

            args = {}
            kwargs = {}
            if with_user:
                args["user"] = user
            else:
                args["user"] = ""
            if with_document:
                kwargs["document"] = None

            mock_ds_service.assert_called_once_with(
                simulation_projet.dossier,
                args["user"],
                motivation="justification",
                **kwargs,
            )


@mock.patch(
    "gsl_simulation.services.simulation_projet_service.SimulationProjetService.accept_a_simulation_projet"
)
def test_update_status_with_accepted(mock_accept_a_simulation_projet, user):
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROCESSING
    )
    new_status = SimulationProjet.STATUS_ACCEPTED

    form = SimulationProjetStatusForm(instance=simulation_projet)
    form.save(new_status, user)

    mock_accept_a_simulation_projet.assert_called_once_with(simulation_projet, user)


@pytest.mark.parametrize(
    ("initial_status"),
    (
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_DISMISSED,
    ),
)
def test_update_status_with_processing_from_accepted_or_refused_or_dismissed(
    initial_status, user
):
    simulation_projet = SimulationProjetFactory(status=initial_status)
    new_status = SimulationProjet.STATUS_PROCESSING

    with mock.patch(
        "gsl_projet.models.DotationProjet.set_back_status_to_processing"
    ) as mock_set_back_a_simulation_projet_to_processing:
        form = SimulationProjetStatusForm(instance=simulation_projet)
        form.save(new_status, user)

        mock_set_back_a_simulation_projet_to_processing.assert_called_once()


def test_update_status_with_processing(user):
    simulation_projet = SimulationProjetFactory(
        status=SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    )
    new_status = SimulationProjet.STATUS_PROCESSING

    form = SimulationProjetStatusForm(instance=simulation_projet)
    form.save(new_status, user)

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == new_status


SIMULATION_PROJET_STATUS_TO_DOTATION_PROJET_STATUS = {
    SimulationProjet.STATUS_ACCEPTED: PROJET_STATUS_ACCEPTED,
    SimulationProjet.STATUS_REFUSED: PROJET_STATUS_REFUSED,
    SimulationProjet.STATUS_PROCESSING: PROJET_STATUS_PROCESSING,
    SimulationProjet.STATUS_DISMISSED: PROJET_STATUS_DISMISSED,
    SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED: PROJET_STATUS_PROCESSING,
}


@pytest.mark.parametrize(
    ("initial_status"),
    (
        SimulationProjet.STATUS_ACCEPTED,
        SimulationProjet.STATUS_REFUSED,
        SimulationProjet.STATUS_DISMISSED,
    ),
)
@pytest.mark.parametrize(
    "new_status",
    (
        SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED,
        SimulationProjet.STATUS_PROVISIONALLY_REFUSED,
    ),
)
def test_update_status_with_provisionally_accepted_from_refused_or_accepted_or_dismissed(
    initial_status, new_status
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

    form = SimulationProjetStatusForm(instance=simulation_projet)
    form.save(new_status, user)

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == new_status
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
def test_update_status_with_provisionally_accepted_remove_programmation_projet_from_accepted_or_refused(
    initial_status, user
):
    dotation_projet = DotationProjetFactory(
        status=SIMULATION_PROJET_STATUS_TO_DOTATION_PROJET_STATUS[initial_status]
    )
    simulation_projet = SimulationProjetFactory(
        status=initial_status,
        dotation_projet=dotation_projet,
    )
    ProgrammationProjetFactory(dotation_projet=simulation_projet.dotation_projet)

    form = SimulationProjetStatusForm(instance=simulation_projet)
    form.save(SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED, user)

    simulation_projet.refresh_from_db()
    assert simulation_projet.status == SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED
    assert (
        ProgrammationProjet.objects.filter(
            dotation_projet=simulation_projet.dotation_projet
        ).count()
        == 0
    )


@mock.patch(
    "gsl_simulation.services.simulation_projet_service.SimulationProjetService._update_ds_assiette_montant_and_taux"
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

    form = SimulationProjetStatusForm(instance=simulation_projet)
    form.save(new_status, user)

    mock_ds_update.assert_called_once_with(
        dossier=simulation_projet.projet.dossier_ds,
        user=user,
        dotation=simulation_projet.dotation,
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
    "gsl_simulation.services.simulation_projet_service.SimulationProjetService._update_ds_assiette_montant_and_taux"
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

    form = SimulationProjetStatusForm(instance=simulation_projet)
    form.save(new_projet_status, user)

    if new_projet_status == SimulationProjet.STATUS_ACCEPTED:
        mock_ds_update.assert_called_once_with(
            dossier=simulation_projet.projet.dossier_ds,
            user=user,
            dotation=simulation_projet.dotation,
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
