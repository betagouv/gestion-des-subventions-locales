"""
Tests for the acceptance validation modal.

When opening the acceptance modal from either the simulation detail page
or the project detail page, the view must validate that:
- DotationProjet.assiette is set
- DotationProjet.assiette >= SimulationProjet.montant

Otherwise a dedicated error modal is rendered with the detailed reasons.
"""

from unittest import mock

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_PROCESSING,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.forms import SimulationProjetStatusForm
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_save_dossier():
    with mock.patch(
        "gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds"
    ):
        yield


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre):
    return CollegueWithDSProfileFactory(perimetre=perimetre)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def detr_enveloppe(perimetre):
    return DetrEnveloppeFactory(perimetre=perimetre, annee=2025, montant=1_000_000)


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


def _make_simulation_projet(collegue, simulation, *, assiette, montant):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
        assiette=assiette,
    )
    dotation_projet.projet.dossier_ds.ds_instructeurs.add(collegue.ds_profile)
    return SimulationProjetFactory(
        dotation_projet=dotation_projet,
        status=SimulationProjet.STATUS_PROCESSING,
        montant=montant,
        simulation=simulation,
    )


def _accept_url(simulation_projet):
    return reverse(
        "simulation:simulation-projet-update-programmed-status",
        args=[simulation_projet.id, SimulationProjet.STATUS_ACCEPTED],
    )


# --- Form-level unit tests ---------------------------------------------------


class TestSimulationProjetStatusFormClean:
    def test_valid_when_assiette_is_greater_than_or_equal_to_montant(
        self, collegue, simulation
    ):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=10_000, montant=5_000
        )
        form = SimulationProjetStatusForm(
            data={},
            instance=simulation_projet,
            status=SimulationProjet.STATUS_ACCEPTED,
        )
        assert form.is_valid(), form.errors

    def test_invalid_when_assiette_is_missing(self, collegue, simulation):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=None, montant=5_000
        )
        form = SimulationProjetStatusForm(
            data={},
            instance=simulation_projet,
            status=SimulationProjet.STATUS_ACCEPTED,
        )
        assert not form.is_valid()
        errors = form.non_field_errors()
        assert len(errors) == 1
        assert "assiette subventionnable est manquante" in errors[0].lower()

    def test_invalid_when_assiette_is_lower_than_montant(self, collegue, simulation):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=3_000, montant=5_000
        )
        form = SimulationProjetStatusForm(
            data={},
            instance=simulation_projet,
            status=SimulationProjet.STATUS_ACCEPTED,
        )
        assert not form.is_valid()
        errors = form.non_field_errors()
        assert len(errors) == 1
        assert "inférieure au montant accordé" in errors[0]

    def test_no_validation_when_status_is_not_accepted(self, collegue, simulation):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=None, montant=5_000
        )
        form = SimulationProjetStatusForm(
            data={},
            instance=simulation_projet,
            status=SimulationProjet.STATUS_REFUSED,
        )
        assert form.is_valid(), form.errors


# --- View integration tests -------------------------------------------------


class TestAcceptanceModalView:
    def test_get_renders_standard_modal_when_assiette_is_sufficient(
        self, client_with_user_logged, collegue, simulation
    ):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=10_000, montant=5_000
        )
        response = client_with_user_logged.get(
            _accept_url(simulation_projet), headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert "htmx/notify_later_confirmation_modal.html" in [
            t.name for t in response.templates if t.name
        ]

    def test_get_renders_error_modal_when_assiette_is_missing(
        self, client_with_user_logged, collegue, simulation
    ):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=None, montant=5_000
        )
        response = client_with_user_logged.get(
            _accept_url(simulation_projet), headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert "htmx/acceptance_errors_modal.html" in [
            t.name for t in response.templates if t.name
        ]
        content = response.content.decode()
        assert "Vous ne pouvez pas accepter cette dotation pour ce projet." in content
        assert "assiette subventionnable est manquante" in content.lower()

    def test_get_renders_error_modal_when_assiette_is_lower_than_montant(
        self, client_with_user_logged, collegue, simulation
    ):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=3_000, montant=5_000
        )
        response = client_with_user_logged.get(
            _accept_url(simulation_projet), headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        assert "htmx/acceptance_errors_modal.html" in [
            t.name for t in response.templates if t.name
        ]
        content = response.content.decode()
        assert "inférieure au montant accordé" in content

    def test_get_renders_error_modal_for_double_dotation_projet(
        self, client_with_user_logged, collegue, simulation
    ):
        """
        Regression: on a DETR+DSIL projet whose DSIL is still PROCESSING, the
        combined projet status is PROCESSING, so the GET-time validation must
        be gated on the requested simulation status (not the combined projet
        status) to still catch assiette < montant on the DETR acceptance.
        """
        projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
        projet.dossier_ds.ds_instructeurs.add(collegue.ds_profile)
        detr_dotation = DotationProjetFactory(
            projet=projet,
            dotation=DOTATION_DETR,
            status=PROJET_STATUS_PROCESSING,
            assiette=3_000,
        )
        DotationProjetFactory(
            projet=projet,
            dotation=DOTATION_DSIL,
            status=PROJET_STATUS_PROCESSING,
            assiette=15_000,
        )
        simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
            simulation=simulation,
        )

        response = client_with_user_logged.get(
            _accept_url(simulation_projet), headers={"HX-Request": "true"}
        )

        assert response.status_code == 200
        assert "htmx/acceptance_errors_modal.html" in [
            t.name for t in response.templates if t.name
        ]
        assert "inférieure au montant accordé" in response.content.decode()

    @mock.patch("gsl_projet.models.DsService.update_ds_annotations_for_one_dotation")
    def test_post_blocks_acceptance_when_validation_fails(
        self,
        mock_update,
        client_with_user_logged,
        collegue,
        simulation,
    ):
        simulation_projet = _make_simulation_projet(
            collegue, simulation, assiette=3_000, montant=5_000
        )
        response = client_with_user_logged.post(
            _accept_url(simulation_projet), {}, headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        simulation_projet.refresh_from_db()
        assert simulation_projet.status == SimulationProjet.STATUS_PROCESSING
        mock_update.assert_not_called()
