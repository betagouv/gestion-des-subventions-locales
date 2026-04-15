import csv
import io

import pytest
from django.test import Client
from django.urls import resolve, reverse
from django.utils import timezone

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
    RequestFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_projet.models import Projet
from gsl_projet.tests.factories import (
    DetrProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)
from gsl_simulation.models import SimulationProjet
from gsl_simulation.tests.factories import (
    SimulationFactory,
    SimulationProjetFactory,
)
from gsl_simulation.views.simulation_views import (
    FilteredProjetsExportView,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_with_departement_perimetre():
    """User with departmental perimeter for accessing simulation pages"""
    perimetre = PerimetreDepartementalFactory()
    return CollegueFactory(perimetre=perimetre)


@pytest.fixture
def client_logged_in(user_with_departement_perimetre):
    """Authenticated client with logged-in user"""
    client = Client()
    client.force_login(user_with_departement_perimetre)
    return client


@pytest.fixture
def detr_envelope(user_with_departement_perimetre):
    """DETR envelope for user's perimeter"""
    return DetrEnveloppeFactory(perimetre=user_with_departement_perimetre.perimetre)


@pytest.fixture
def dsil_envelope(user_with_departement_perimetre):
    """DSIL envelope for user's perimeter"""
    return DsilEnveloppeFactory(perimetre=user_with_departement_perimetre.perimetre)


@pytest.fixture
def double_dotation_projet(user_with_departement_perimetre):
    """Project eligible for both DETR and DSIL (double dotation)"""
    projet = ProjetFactory(
        dossier_ds__perimetre=user_with_departement_perimetre.perimetre
    )
    # Create both DETR and DSIL dotations for same project
    detr_dotation = DetrProjetFactory(projet=projet)
    dsil_dotation = DsilProjetFactory(projet=projet)
    return projet, detr_dotation, dsil_dotation


@pytest.mark.parametrize(
    "export_type, content_type",
    (
        ("csv", "text/csv"),
        (
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("xls", "application/vnd.ms-excel"),
        ("ods", "application/vnd.oasis.opendocument.spreadsheet"),
    ),
)
def test_get_filter_projets_export_view(export_type, content_type):
    ### Arrange
    perimetre = PerimetreDepartementalFactory()
    user = CollegueFactory(perimetre=perimetre)
    simulation = SimulationFactory(
        title="Ma Simulation",
        enveloppe__dotation=DOTATION_DSIL,
        enveloppe__perimetre=perimetre,
    )
    SimulationProjetFactory.create_batch(
        2,
        dotation_projet__dotation=DOTATION_DSIL,
        simulation=simulation,
        status=SimulationProjet.STATUS_ACCEPTED,
    )
    SimulationProjetFactory.create_batch(
        3,
        dotation_projet__dotation=DOTATION_DSIL,
        simulation=simulation,
        status=SimulationProjet.STATUS_REFUSED,
    )
    projets = Projet.objects.all()
    assert projets.count() == 5
    today = timezone.now().strftime("%Y-%m-%d")

    ### Act
    req = RequestFactory(user=user)
    view = FilteredProjetsExportView()
    kwargs = {"slug": simulation.slug, "type": export_type}
    url = reverse("simulation:simulation-projets-export", kwargs=kwargs)
    request = req.get(url, data={"status": [SimulationProjet.STATUS_ACCEPTED]})
    request.resolver_match = resolve(url)
    view.request = request
    view.kwargs = kwargs
    response = view.get(request)

    ### Assert
    assert response.status_code == 200
    assert response["Content-Disposition"] == (
        f'attachment; filename="{today} simulation Ma Simulation.{export_type}"'
    )
    assert response["Content-Type"] == content_type

    if export_type == "csv":
        csv_content = response.content.decode("utf-8")
        csv_lines = list(csv.reader(io.StringIO(csv_content)))
        assert len(csv_lines) == 3  # 1 header + 2 projets acceptés


class TestDoubleDotationDisplayOnDetrSimulation:
    """Tests for displaying DSIL info under DETR simulation projects"""

    def test_detr_simulation_page_displays_dsil_information(
        self, client_logged_in, detr_envelope, double_dotation_projet, dsil_envelope
    ):
        """
        When viewing DETR simulation page, DSIL information should be displayed
        under each project line for user information
        """
        projet, detr_dotation, dsil_dotation = double_dotation_projet

        # Create DETR simulation with the DETR-specific envelope
        detr_simulation = SimulationFactory(enveloppe=detr_envelope)
        dsil_simulation = SimulationFactory(enveloppe=dsil_envelope)

        SimulationProjetFactory(
            simulation=detr_simulation, dotation_projet=detr_dotation
        )
        SimulationProjetFactory(
            simulation=dsil_simulation, dotation_projet=dsil_dotation
        )

        # Access DETR simulation detail page
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": detr_simulation.slug},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check for DETR project main row
        assert str(projet.dossier_ds.projet_intitule) in content
        # Check for other-dotation row indicating DSIL information
        assert "gsl-projet-table__row--other-dotation" in content
        assert "Informations pour la dotation DSIL" in content

    def test_detr_simulation_shows_both_dotation_amounts(
        self, client_logged_in, detr_envelope, double_dotation_projet, dsil_envelope
    ):
        """
        DETR simulation should show DETR amounts in main row and DSIL amounts
        in other-dotation row
        """
        projet, detr_dotation, dsil_dotation = double_dotation_projet
        detr_simulation = SimulationFactory(enveloppe=detr_envelope)
        dsil_simulation = SimulationFactory(enveloppe=dsil_envelope)

        SimulationProjetFactory(
            simulation=detr_simulation,
            dotation_projet=detr_dotation,
            montant=5000,
        )
        SimulationProjetFactory(
            simulation=dsil_simulation,
            dotation_projet=dsil_dotation,
            montant=3000,
        )

        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": detr_simulation.slug},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "5\xa0000" in content
        assert "3\xa0000" in content

    def test_single_dotation_projet_no_secondary_row(
        self, client_logged_in, detr_envelope
    ):
        """
        Projects with only DETR dotation should not display secondary row
        """
        perimetre = detr_envelope.perimetre
        projet = ProjetFactory(dossier_ds__perimetre=perimetre)
        detr_dotation = DetrProjetFactory(projet=projet)

        detr_simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=detr_simulation, dotation_projet=detr_dotation
        )

        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": detr_simulation.slug},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "gsl-projet-table__row--other-dotation" not in content


class TestNotifiedProjectDisplayOnSimulationTable:
    """Tests for display of notified projects in simulation table (text instead of forms)"""

    def test_notified_project_shows_text_instead_of_montant_and_dotation_form(
        self, client_logged_in, detr_envelope
    ):
        """
        Notified projects should show montant as text instead of input field
        """
        perimetre = detr_envelope.perimetre
        projet = ProjetFactory(
            dossier_ds__perimetre=perimetre, notified_at=timezone.now()
        )
        detr_dotation = DetrProjetFactory(projet=projet)

        detr_simulation = SimulationFactory(enveloppe=detr_envelope)
        simu = SimulationProjetFactory(
            simulation=detr_simulation,
            dotation_projet=detr_dotation,
            montant=5000,
        )

        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": detr_simulation.slug},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        # Should NOT have the montant edit button for notified projects
        assert f"edit-montant/{simu.id}/" not in content
        # Should show formatted amount
        assert "5\xa0000" in content
        # Should NOT have the dotation dropdown form for notified projects
        assert "simulation-projet-dotation-form" not in content
        # Should show dotation as text
        assert "DETR" in content

    def test_non_notified_project_shows_forms(self, client_logged_in, detr_envelope):
        """
        Non-notified projects should still show editable forms
        """
        perimetre = detr_envelope.perimetre
        projet = ProjetFactory(dossier_ds__perimetre=perimetre, notified_at=None)
        detr_dotation = DetrProjetFactory(projet=projet)

        detr_simulation = SimulationFactory(enveloppe=detr_envelope)
        simu = SimulationProjetFactory(
            simulation=detr_simulation, dotation_projet=detr_dotation
        )

        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": detr_simulation.slug},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        # Should have the dotation dropdown form
        assert "simulation-projet-dotation-form" in content
        # Should have the montant edit button
        assert f"edit-montant/{simu.id}/" in content


class TestExportColumnsVisibility:
    """Tests that the export respects the simulation's columns_visibility setting."""

    def _export_csv(self, simulation, user):
        req = RequestFactory(user=user)
        view = FilteredProjetsExportView()
        kwargs = {"slug": simulation.slug, "type": "csv"}
        url = reverse("simulation:simulation-projets-export", kwargs=kwargs)
        request = req.get(url)
        request.resolver_match = resolve(url)
        view.request = request
        view.kwargs = kwargs
        response = view.get(request)
        assert response.status_code == 200
        csv_content = response.content.decode("utf-8")
        return list(csv.reader(io.StringIO(csv_content), delimiter=";"))

    def test_export_with_hidden_columns_excludes_them(self):
        perimetre = PerimetreDepartementalFactory()
        user = CollegueFactory(perimetre=perimetre)
        simulation = SimulationFactory(
            title="Export Test",
            enveloppe__dotation=DOTATION_DSIL,
            enveloppe__perimetre=perimetre,
            columns_visibility={
                "date-depot": True,
                "demandeur": False,
                "arrondissement": False,
                "comment-1": False,
            },
        )
        SimulationProjetFactory(
            dotation_projet__dotation=DOTATION_DSIL,
            simulation=simulation,
        )

        csv_lines = self._export_csv(simulation, user)
        headers = csv_lines[0]

        assert "Date de dépôt du dossier" in headers
        assert "Demandeur" not in headers
        assert "Arrondissement du demandeur" not in headers
        assert "Commentaire 1" not in headers

    def test_export_with_null_visibility_hides_non_default_columns(self):
        perimetre = PerimetreDepartementalFactory()
        user = CollegueFactory(perimetre=perimetre)
        simulation = SimulationFactory(
            title="Default Export",
            enveloppe__dotation=DOTATION_DSIL,
            enveloppe__perimetre=perimetre,
            columns_visibility=None,
        )
        SimulationProjetFactory(
            dotation_projet__dotation=DOTATION_DSIL,
            simulation=simulation,
        )

        csv_lines = self._export_csv(simulation, user)
        headers = csv_lines[0]

        # displayed_by_default=False columns should be excluded
        assert "Arrondissement du demandeur" not in headers
        assert "Date de début des travaux" not in headers
        assert "Date de fin des travaux" not in headers
        assert "Champ libre 1" not in headers
        assert "Budget vert (demandeur)" not in headers
        assert "Dossier complet" not in headers
        assert "Commentaire 1" not in headers
        assert "Commentaire 2" not in headers
        assert "Commentaire 3" not in headers
        # displayed_by_default=True columns should be included
        assert "Date de dépôt du dossier" in headers
        assert "Demandeur" in headers
        assert "Montant prévisionnel accordé" in headers

    def test_export_with_nom_demandeur_visibility(self):
        perimetre = PerimetreDepartementalFactory()
        user = CollegueFactory(perimetre=perimetre)
        simulation = SimulationFactory(
            title="Nom Demandeur",
            enveloppe__dotation=DOTATION_DSIL,
            enveloppe__perimetre=perimetre,
            columns_visibility={
                "nom-demandeur": True,
            },
        )
        SimulationProjetFactory(
            dotation_projet__dotation=DOTATION_DSIL,
            simulation=simulation,
        )

        csv_lines = self._export_csv(simulation, user)
        headers = csv_lines[0]

        assert "Nom et prénom du demandeur" in headers

    def test_export_hides_nom_demandeur_when_not_visible(self):
        perimetre = PerimetreDepartementalFactory()
        user = CollegueFactory(perimetre=perimetre)
        simulation = SimulationFactory(
            title="Nom Demandeur Hidden",
            enveloppe__dotation=DOTATION_DSIL,
            enveloppe__perimetre=perimetre,
            columns_visibility={
                "nom-demandeur": False,
            },
        )
        SimulationProjetFactory(
            dotation_projet__dotation=DOTATION_DSIL,
            simulation=simulation,
        )

        csv_lines = self._export_csv(simulation, user)
        headers = csv_lines[0]

        assert "Nom et prénom du demandeur" not in headers

    def test_export_detr_includes_detr_specific_fields(self):
        perimetre = PerimetreDepartementalFactory()
        user = CollegueFactory(perimetre=perimetre)
        simulation = SimulationFactory(
            title="DETR Export",
            enveloppe__dotation=DOTATION_DETR,
            enveloppe__perimetre=perimetre,
            columns_visibility={"date-depot": False},
        )
        SimulationProjetFactory(
            dotation_projet__dotation=DOTATION_DETR,
            simulation=simulation,
        )

        csv_lines = self._export_csv(simulation, user)
        headers = csv_lines[0]

        # DETR-specific fields always present
        assert "Montant demandé supérieur à 100 000€ ?" in headers
        assert "Avis de la commission" in headers
        # Hidden column excluded
        assert "Date de dépôt du dossier" not in headers


class TestFilterPersistence:
    """Tests that simulation filters are saved to and restored from the Simulation model."""

    def test_filters_saved_on_simulation(self, client_logged_in, detr_envelope):
        simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        client_logged_in.get(url, {"status": "draft", "porteur": "epci"})

        simulation.refresh_from_db()
        assert simulation.filters == {
            "status": ["draft"],
            "porteur": ["epci"],
        }

    def test_filters_restored_from_simulation(self, client_logged_in, detr_envelope):
        simulation = SimulationFactory(
            enveloppe=detr_envelope, filters={"status": ["draft"]}
        )
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        response = client_logged_in.get(url)
        assert response.status_code == 302
        assert "status=draft" in response.url

    def test_no_redirect_when_no_saved_filters(self, client_logged_in, detr_envelope):
        simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        response = client_logged_in.get(url)
        assert response.status_code == 200

    def test_reset_clears_filters(self, client_logged_in, detr_envelope):
        simulation = SimulationFactory(
            enveloppe=detr_envelope, filters={"status": ["draft"]}
        )
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        client_logged_in.get(url, {"reset_filters": "1"})

        simulation.refresh_from_db()
        assert simulation.filters is None

    def test_page_param_not_saved_as_filter(self, client_logged_in, detr_envelope):
        simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        client_logged_in.get(url, {"status": "draft", "page": "1"})

        simulation.refresh_from_db()
        assert "page" not in simulation.filters

    def test_page_only_does_not_save_and_does_not_redirect(
        self, client_logged_in, detr_envelope
    ):
        simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        response = client_logged_in.get(url, {"page": "1"})
        assert response.status_code == 200
        simulation.refresh_from_db()
        assert simulation.filters is None

    def test_order_param_not_saved_as_filter(self, client_logged_in, detr_envelope):
        simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        response = client_logged_in.get(url, {"order": "-montant_previsionnel"})
        assert response.status_code == 200
        simulation.refresh_from_db()
        assert simulation.filters is None

    def test_empty_string_values_not_saved(self, client_logged_in, detr_envelope):
        simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        response = client_logged_in.get(url, {"cout_min": "", "cout_max": ""})
        assert response.status_code == 200
        simulation.refresh_from_db()
        assert simulation.filters is None

    def test_filters_scoped_per_simulation(self, client_logged_in, detr_envelope):
        sim1 = SimulationFactory(enveloppe=detr_envelope)
        sim2 = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=sim1, dotation_projet__dotation=DOTATION_DETR
        )
        SimulationProjetFactory(
            simulation=sim2, dotation_projet__dotation=DOTATION_DETR
        )

        url1 = reverse("gsl_simulation:simulation-detail", kwargs={"slug": sim1.slug})
        url2 = reverse("gsl_simulation:simulation-detail", kwargs={"slug": sim2.slug})

        client_logged_in.get(url1, {"status": "draft"})
        client_logged_in.get(url2, {"porteur": "epci"})

        sim1.refresh_from_db()
        sim2.refresh_from_db()
        assert sim1.filters == {"status": ["draft"]}
        assert sim2.filters == {"porteur": ["epci"]}

    def test_filters_persist_across_users(
        self, client_logged_in, user_with_departement_perimetre, detr_envelope
    ):
        simulation = SimulationFactory(enveloppe=detr_envelope)
        SimulationProjetFactory(
            simulation=simulation,
            dotation_projet__dotation=DOTATION_DETR,
        )
        url = reverse(
            "gsl_simulation:simulation-detail",
            kwargs={"slug": simulation.slug},
        )

        client_logged_in.get(url, {"status": "draft"})

        other_user = CollegueFactory(
            perimetre=user_with_departement_perimetre.perimetre
        )
        other_client = Client()
        other_client.force_login(other_user)

        response = other_client.get(url)
        assert response.status_code == 302
        assert "status=draft" in response.url
