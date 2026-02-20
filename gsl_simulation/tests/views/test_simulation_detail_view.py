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
from gsl_projet.constants import DOTATION_DSIL
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
    simulation = SimulationFactory(
        title="Ma Simulation", enveloppe__dotation=DOTATION_DSIL
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
    req = RequestFactory()
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
        # Should NOT have the montant input form for this simulation projet
        assert f'id="id-montant-{simu.id}"' not in content
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
        # Should have the montant input form
        assert f'id="id-montant-{simu.id}"' in content
