from unittest import mock

import pytest

from gsl_core.tests.factories import CollegueFactory
from gsl_simulation.forms import DismissProjetForm, RefuseProjetForm
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("ds_service, dotation_projet_transition, form_class"),
    (
        (
            ("gsl_simulation.forms.DsMutator.dossier_refuser", False, True),
            ("refuse", True, False),
            RefuseProjetForm,
        ),
        (
            ("gsl_simulation.forms.DsService.dismiss_in_ds", True, False),
            ("dismiss", True, False),
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
    (dotation_projet_transition, with_enveloppe, with_montant) = (
        dotation_projet_transition
    )
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
            form.save(user=user)
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
