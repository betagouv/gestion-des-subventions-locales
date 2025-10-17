from unittest import mock

import pytest

from gsl_simulation.forms import RefuseProjetForm
from gsl_simulation.tests.factories import SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("dotation_projet_transition, form_class, with_enveloppe, with_montant"),
    (("refuse", RefuseProjetForm, True, False),),
)
@mock.patch("gsl_simulation.forms.DsMutator.dossier_refuser")
def test_simulation_projet_transition_are_called(
    mock_dossier_refuser,
    dotation_projet_transition,
    form_class,
    with_enveloppe,
    with_montant,
):
    simulation_projet = SimulationProjetFactory()
    with mock.patch(
        f"gsl_projet.models.DotationProjet.{dotation_projet_transition}",
        wraps=getattr(simulation_projet.dotation_projet, dotation_projet_transition),
    ) as mock_transition_dotation_projet:
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
        form.save("instruct_id")
        mock_transition_dotation_projet.assert_called_once_with(**args, **kwargs)
        mock_dossier_refuser.assert_called_once_with(
            simulation_projet.dossier, "instruct_id", motivation="justification"
        )
