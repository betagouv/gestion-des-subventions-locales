"""
Tests for displaying other dotation information on DETR/DSIL programming pages.

When viewing a DETR programming page, DSIL information should be displayed under each
project line for user reference. Same applies when viewing DSIL page showing DETR info.
"""

import pytest
from django.test import Client
from django.urls import reverse

from gsl.core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.projet.tests.factories import (
    DetrProjetFactory,
    DsilProjetFactory,
    ProjetFactory,
)
from gsl.simulation.tests.factories import SimulationFactory, SimulationProjetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_with_departement_perimetre():
    """User with departmental perimeter for accessing programmation pages"""
    collegue = CollegueFactory()
    perimetre = PerimetreDepartementalFactory()
    collegue.perimetre = perimetre
    collegue.save()
    return collegue


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
def double_enveloppe_projet(user_with_departement_perimetre):
    """Project eligible for both DETR and DSIL (double dotation)"""
    projet = ProjetFactory(
        dossier_ds__perimetre=user_with_departement_perimetre.perimetre
    )
    # Create both DETR and DSIL dotations for same project
    detr_dotation = DetrProjetFactory(projet=projet)
    dsil_dotation = DsilProjetFactory(projet=projet)
    return projet, detr_dotation, dsil_dotation


class TestDoubleDotationDisplayOnDetrProgrammation:
    """Tests for displaying DSIL info under DETR programming projects"""

    def test_detr_programming_page_displays_dsil_information(
        self, client_logged_in, detr_envelope, dsil_envelope, double_enveloppe_projet
    ):
        """
        When viewing DETR programming page, DSIL information should be displayed
        under each project line for user information
        """
        projet, detr_dotation, dsil_dotation = double_enveloppe_projet

        # Create programming for both dotations
        detr_dotation.accept_without_ds_update(montant=0, enveloppe=detr_envelope)
        detr_dotation.save()

        # Access DETR programming page
        url = reverse(
            "programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Check for DETR project main row
        assert str(projet.dossier_ds.projet_intitule) in content

        # Check for other-dotation row indicating DSIL information
        assert "gsl-projet-table__row--other-dotation" in content
        assert "Informations pour la dotation DSIL" in content

    def test_detr_programming_page_shows_dsil_amount(
        self, client_logged_in, detr_envelope, dsil_envelope, double_enveloppe_projet
    ):
        """DSIL amount should be displayed in the other dotation row"""
        projet, detr_dotation, dsil_dotation = double_enveloppe_projet

        detr_dotation.accept_without_ds_update(montant=5000, enveloppe=detr_envelope)
        detr_dotation.save()
        SimulationProjetFactory(
            enveloppe_projet=dsil_dotation,
            simulation=SimulationFactory(enveloppe=dsil_envelope),
            montant=3000,  # DSIL amount
        )

        url = reverse(
            "programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # DSIL amount should be displayed in other-dotation row
        # The actual format depends on template rendering
        assert "gsl-projet-table__row--other-dotation" in content
        assert "3\xa0000" in content

    def test_single_dotation_projects_dont_show_other_row(
        self, client_logged_in, detr_envelope
    ):
        """
        Projects with only DETR dotation should NOT show other-dotation row
        """
        # Create project with only DETR dotation
        projet = ProjetFactory()
        detr_dotation = DetrProjetFactory(projet=projet)

        detr_dotation.accept_without_ds_update(montant=0, enveloppe=detr_envelope)
        detr_dotation.save()

        url = reverse(
            "programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        response = client_logged_in.get(url)

        assert response.status_code == 200
        content = response.content.decode()

        # Should have main row for DETR project
        assert str(projet.dossier_ds.projet_intitule) in content

        # Count other-dotation rows - there should be none for single-dotation projects
        other_rows_count = content.count("gsl-projet-table__row--other-dotation")
        assert other_rows_count == 0
