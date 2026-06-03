"""
Tests for ProgrammationStatusUpdateView with double dotation projects.

Since notification is now decoupled from the status change, the view always
uses ``SimulationProjetStatusForm`` and the ``programmation_status_change_modal``
template, regardless of whether the resulting projet status will be
ACCEPTED, REFUSED, DISMISSED or stay PROCESSING.
"""

from unittest import mock

import pytest
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import DetrEnveloppeFactory, DsilEnveloppeFactory
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def double_dotation_projet(collegue):
    projet = ProjetFactory(dossier_ds__perimetre=collegue.perimetre)
    projet.dossier_ds.ds_instructeurs.add(collegue.ds_profile)

    detr_dotation = DotationProjetFactory(
        projet=projet,
        dotation=DOTATION_DETR,
        status=PROJET_STATUS_PROCESSING,
        assiette=10_000,
    )
    dsil_dotation = DotationProjetFactory(
        projet=projet,
        dotation=DOTATION_DSIL,
        status=PROJET_STATUS_PROCESSING,
        assiette=15_000,
    )
    return {
        "projet": projet,
        "detr_dotation": detr_dotation,
        "dsil_dotation": dsil_dotation,
    }


def _assert_uses_notify_later_modal(response):
    assert response.status_code == 200
    assert "htmx/programmation_status_change_modal.html" in [
        t.name for t in response.templates
    ]


class TestModalForRefusing:
    def test_refuse_detr_with_dsil_processing(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        projet = double_dotation_projet["projet"]

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        _assert_uses_notify_later_modal(response)
        assert response.context["new_projet_status"] == PROJET_STATUS_PROCESSING
        assert (
            response.context["new_simulation_status"] == SimulationProjet.STATUS_REFUSED
        )

    def test_refuse_detr_with_dsil_already_refused(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        dsil_dotation.status = PROJET_STATUS_REFUSED
        dsil_dotation.save()

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        _assert_uses_notify_later_modal(response)
        assert response.context["new_projet_status"] == PROJET_STATUS_REFUSED

    def test_refuse_detr_with_dsil_accepted(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        dsil_dotation.status = PROJET_STATUS_ACCEPTED
        dsil_dotation.save()

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        _assert_uses_notify_later_modal(response)
        assert response.context["new_projet_status"] == PROJET_STATUS_ACCEPTED


class TestModalForDismissing:
    def test_dismiss_dsil_with_detr_processing(
        self, client_with_user_logged, double_dotation_projet
    ):
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[dsil_simulation_projet.id, SimulationProjet.STATUS_DISMISSED],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        _assert_uses_notify_later_modal(response)
        assert response.context["new_projet_status"] == PROJET_STATUS_PROCESSING

    def test_dismiss_dsil_with_detr_dismissed(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        detr_dotation.status = PROJET_STATUS_DISMISSED
        detr_dotation.save()

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[dsil_simulation_projet.id, SimulationProjet.STATUS_DISMISSED],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        _assert_uses_notify_later_modal(response)
        assert response.context["new_projet_status"] == PROJET_STATUS_DISMISSED

    def test_dismiss_dsil_with_detr_refused(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        detr_dotation.status = PROJET_STATUS_REFUSED
        detr_dotation.save()

        dsil_enveloppe = DsilEnveloppeFactory(perimetre=projet.perimetre)
        dsil_simulation = SimulationFactory(enveloppe=dsil_enveloppe)
        dsil_simulation_projet = SimulationProjetFactory(
            dotation_projet=dsil_dotation,
            simulation=dsil_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=7_500,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[dsil_simulation_projet.id, SimulationProjet.STATUS_DISMISSED],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        _assert_uses_notify_later_modal(response)
        assert response.context["new_projet_status"] == PROJET_STATUS_DISMISSED


class TestModalForAccepting:
    def test_accept_detr_with_dsil_processing(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        projet = double_dotation_projet["projet"]

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_ACCEPTED],
        )
        response = client_with_user_logged.get(url, headers={"HX-Request": "true"})

        _assert_uses_notify_later_modal(response)


class TestPostNoLongerPushesDsAtStatusChange:
    def test_post_refuse_with_both_refused_does_not_call_ds(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        dsil_dotation = double_dotation_projet["dsil_dotation"]
        projet = double_dotation_projet["projet"]

        dsil_dotation.status = PROJET_STATUS_REFUSED
        dsil_dotation.save()

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )
        with mock.patch(
            "gsl_demarches_simplifiees.ds_client.DsMutator.dossier_refuser"
        ) as mock_ds_refuser:
            response = client_with_user_logged.post(
                url, {}, headers={"HX-Request": "true"}
            )

        assert response.status_code == 200
        mock_ds_refuser.assert_not_called()
        projet.refresh_from_db()
        assert projet.notified_at is None

    def test_post_refuse_with_dsil_processing_no_ds_call(
        self, client_with_user_logged, double_dotation_projet
    ):
        detr_dotation = double_dotation_projet["detr_dotation"]
        projet = double_dotation_projet["projet"]

        detr_enveloppe = DetrEnveloppeFactory(perimetre=projet.perimetre)
        detr_simulation = SimulationFactory(enveloppe=detr_enveloppe)
        detr_simulation_projet = SimulationProjetFactory(
            dotation_projet=detr_dotation,
            simulation=detr_simulation,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=5_000,
        )

        url = reverse(
            "gsl_simulation:simulation-projet-update-programmed-status",
            args=[detr_simulation_projet.id, SimulationProjet.STATUS_REFUSED],
        )
        response = client_with_user_logged.post(url, {}, headers={"HX-Request": "true"})

        assert response.status_code == 200
        projet.refresh_from_db()
        assert projet.notified_at is None
