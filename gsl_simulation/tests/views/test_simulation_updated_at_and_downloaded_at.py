from typing import cast
from unittest import mock

import pytest
from django.test import Client
from django.urls import resolve, reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    CollegueWithDSProfileFactory,
    PerimetreDepartementalFactory,
    RequestFactory,
)
from gsl_demarches_simplifiees.tests.factories import FieldMappingFactory
from gsl_programmation.tests.factories import DetrEnveloppeFactory
from gsl_projet.constants import DOTATION_DETR, PROJET_STATUS_PROCESSING
from gsl_projet.tests.factories import DotationProjetFactory
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import SimulationFactory, SimulationProjetFactory
from gsl_simulation.views.simulation_views import FilteredProjetsExportView

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre_departemental():
    return PerimetreDepartementalFactory()


@pytest.fixture
def ds_field():
    return FieldMappingFactory(ds_field_id=101112)


@pytest.fixture
def detr_enveloppe(perimetre_departemental):
    return DetrEnveloppeFactory(
        perimetre=perimetre_departemental, annee=2025, montant=1_000_000
    )


@pytest.fixture
def simulation(detr_enveloppe):
    return SimulationFactory(enveloppe=detr_enveloppe)


@pytest.fixture
def collegue(perimetre_departemental):
    return CollegueWithDSProfileFactory(perimetre=perimetre_departemental)


@pytest.fixture
def client_with_user_logged(collegue):
    return ClientWithLoggedUserFactory(collegue)


@pytest.fixture
def simulation_projet(collegue, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    return cast(
        SimulationProjet,
        SimulationProjetFactory(
            dotation_projet=dotation_projet,
            status=SimulationProjet.STATUS_PROCESSING,
            montant=1_000,
            simulation=simulation,
        ),
    )


@pytest.fixture
def accepted_simulation_projet(collegue, simulation):
    dotation_projet = DotationProjetFactory(
        status=PROJET_STATUS_PROCESSING,
        projet__dossier_ds__perimetre=collegue.perimetre,
        dotation=DOTATION_DETR,
        assiette=10_000,
    )
    return cast(
        SimulationProjet,
        SimulationProjetFactory(
            dotation_projet=dotation_projet,
            status=SimulationProjet.STATUS_ACCEPTED,
            montant=1_000,
            simulation=simulation,
        ),
    )


class TestSimulationUpdatedAtOnFieldChange:
    """Simulation.updated_at se met à jour quand montant, taux ou assiette changent."""

    def test_edit_montant_updates_simulation_updated_at(
        self, client_with_user_logged, simulation_projet
    ):
        before = simulation_projet.simulation.updated_at
        url = reverse("simulation:edit-montant", args=[simulation_projet.id])
        client_with_user_logged.post(
            url, {"montant": "2000"}, headers={"HX-Request": "true"}
        )
        simulation_projet.simulation.refresh_from_db()
        assert simulation_projet.simulation.updated_at > before

    def test_edit_assiette_updates_simulation_updated_at(
        self, client_with_user_logged, simulation_projet
    ):
        before = simulation_projet.simulation.updated_at
        url = reverse("simulation:edit-assiette", args=[simulation_projet.id])
        client_with_user_logged.post(
            url, {"assiette": "5000"}, headers={"HX-Request": "true"}
        )
        simulation_projet.simulation.refresh_from_db()
        assert simulation_projet.simulation.updated_at > before

    @mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    )
    def test_edit_taux_updates_simulation_updated_at(
        self, _mock_ds, client_with_user_logged, accepted_simulation_projet
    ):
        before = accepted_simulation_projet.simulation.updated_at
        url = reverse("simulation:edit-taux", args=[accepted_simulation_projet.id])
        client_with_user_logged.post(
            url, {"taux": "50"}, headers={"HX-Request": "true"}
        )
        accepted_simulation_projet.simulation.refresh_from_db()
        assert accepted_simulation_projet.simulation.updated_at > before


class TestSimulationUpdatedAtOnStatusChange:
    """Simulation.updated_at se met à jour lors des changements de statut,
    et seulement pour la simulation à l'origine de l'action."""

    def test_simulation_status_provisionally_accepted_updates_simulation_updated_at(
        self, client_with_user_logged, simulation_projet
    ):
        before = simulation_projet.simulation.updated_at
        page_url = reverse(
            "simulation:simulation-projet-detail", args=[simulation_projet.id]
        )
        url = reverse(
            "simulation:simulation-projet-update-simulation-status",
            args=[simulation_projet.id, SimulationProjet.STATUS_PROVISIONALLY_ACCEPTED],
        )
        client_with_user_logged.post(
            url,
            headers={"HX-Request": "true", "HX-Request-URL": page_url},
            follow=True,
        )
        simulation_projet.simulation.refresh_from_db()
        assert simulation_projet.simulation.updated_at > before

    def test_simulation_status_provisionally_refused_updates_simulation_updated_at(
        self, client_with_user_logged, simulation_projet
    ):
        before = simulation_projet.simulation.updated_at
        page_url = reverse(
            "simulation:simulation-projet-detail", args=[simulation_projet.id]
        )
        url = reverse(
            "simulation:simulation-projet-update-simulation-status",
            args=[simulation_projet.id, SimulationProjet.STATUS_PROVISIONALLY_REFUSED],
        )
        client_with_user_logged.post(
            url,
            headers={"HX-Request": "true", "HX-Request-URL": page_url},
            follow=True,
        )
        simulation_projet.simulation.refresh_from_db()
        assert simulation_projet.simulation.updated_at > before

    @mock.patch("gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds")
    @mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    )
    def test_programmation_status_accept_updates_simulation_updated_at(
        self, _mock_ds, _mock_save, client_with_user_logged, simulation_projet
    ):
        before = simulation_projet.simulation.updated_at
        page_url = reverse(
            "simulation:simulation-detail", args=[simulation_projet.simulation.slug]
        )
        url = reverse(
            "simulation:simulation-projet-update-programmed-status",
            args=[simulation_projet.id, SimulationProjet.STATUS_ACCEPTED],
        )
        client_with_user_logged.post(
            url,
            follow=True,
            headers={"HX-Request": "true", "HX-Request-URL": page_url},
        )
        simulation_projet.simulation.refresh_from_db()
        assert simulation_projet.simulation.updated_at > before

    @mock.patch("gsl_simulation.views.simulation_projet_views.save_one_dossier_from_ds")
    @mock.patch(
        "gsl_demarches_simplifiees.services.DsService.update_ds_annotations_for_one_dotation"
    )
    def test_accept_does_not_update_other_simulations_updated_at(
        self, _mock_ds, _mock_save, client_with_user_logged, simulation_projet
    ):
        """Quand on accepte un simulation_projet, la cascade met à jour tous les
        SimulationProjet liés au même DotationProjet, mais on ne doit mettre à
        jour l'updated_at que de la simulation à l'origine de l'action."""
        other_simulation = SimulationFactory(
            enveloppe=simulation_projet.simulation.enveloppe
        )
        SimulationProjetFactory(
            dotation_projet=simulation_projet.dotation_projet,
            simulation=other_simulation,
            montant=1_000,
            status=SimulationProjet.STATUS_PROCESSING,
        )
        before_other = other_simulation.updated_at

        page_url = reverse(
            "simulation:simulation-detail", args=[simulation_projet.simulation.slug]
        )
        url = reverse(
            "simulation:simulation-projet-update-programmed-status",
            args=[simulation_projet.id, SimulationProjet.STATUS_ACCEPTED],
        )
        client_with_user_logged.post(
            url,
            follow=True,
            headers={"HX-Request": "true", "HX-Request-URL": page_url},
        )

        other_simulation.refresh_from_db()
        assert other_simulation.updated_at == before_other


class TestSimulationUpdatedAtOnFilterChange:
    """Simulation.updated_at se met à jour lors des changements de filtres."""

    def test_adding_filter_updates_simulation_updated_at(self, collegue, simulation):
        client = Client()
        client.force_login(collegue)
        before = simulation.updated_at
        url = reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
        client.get(url, {"status": SimulationProjet.STATUS_PROCESSING})
        simulation.refresh_from_db()
        assert simulation.updated_at > before

    def test_resetting_filters_updates_simulation_updated_at(
        self, collegue, simulation
    ):
        simulation.filters = {"status": [SimulationProjet.STATUS_PROCESSING]}
        simulation.save(update_fields=["filters"])
        before = simulation.updated_at

        client = Client()
        client.force_login(collegue)
        url = reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
        client.get(url, {"reset_filters": "1"})

        simulation.refresh_from_db()
        assert simulation.updated_at > before

    def test_same_filters_do_not_update_simulation_updated_at(
        self, collegue, simulation
    ):
        """Si les filtres n'ont pas changé, updated_at ne doit pas être mis à jour."""
        simulation.filters = {"status": [SimulationProjet.STATUS_PROCESSING]}
        simulation.save(update_fields=["filters"])
        before = simulation.updated_at

        client = Client()
        client.force_login(collegue)
        url = reverse("simulation:simulation-detail", kwargs={"slug": simulation.slug})
        # Le GET avec les mêmes filtres déclenche un redirect (filtres déjà sauvegardés),
        # sans re-sauvegarder l'updated_at.
        client.get(url, {"status": SimulationProjet.STATUS_PROCESSING})

        simulation.refresh_from_db()
        assert simulation.updated_at == before


class TestSimulationDownloadedAt:
    """Simulation.downloaded_at est sauvegardé lors du téléchargement."""

    def test_export_sets_downloaded_at(self, simulation):
        assert simulation.downloaded_at is None

        perimetre = simulation.enveloppe.perimetre
        user = CollegueFactory(perimetre=perimetre)
        req = RequestFactory(user=user)
        view = FilteredProjetsExportView()
        kwargs = {"slug": simulation.slug, "type": "csv"}
        url = reverse("simulation:simulation-projets-export", kwargs=kwargs)
        request = req.get(url)
        request.resolver_match = resolve(url)
        view.request = request
        view.kwargs = kwargs

        before = timezone.now()
        view.get(request)

        simulation.refresh_from_db()
        assert simulation.downloaded_at is not None
        assert simulation.downloaded_at >= before

    def test_export_updates_downloaded_at_on_subsequent_call(self, simulation):
        from datetime import timedelta

        simulation.downloaded_at = timezone.now() - timedelta(days=1)
        simulation.save(update_fields=["downloaded_at"])
        first_downloaded_at = simulation.downloaded_at

        perimetre = simulation.enveloppe.perimetre
        user = CollegueFactory(perimetre=perimetre)
        req = RequestFactory(user=user)
        view = FilteredProjetsExportView()
        kwargs = {"slug": simulation.slug, "type": "csv"}
        url = reverse("simulation:simulation-projets-export", kwargs=kwargs)
        request = req.get(url)
        request.resolver_match = resolve(url)
        view.request = request
        view.kwargs = kwargs
        view.get(request)

        simulation.refresh_from_db()
        assert simulation.downloaded_at > first_downloaded_at
