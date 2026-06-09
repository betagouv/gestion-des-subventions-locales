import pytest
from django.test import Client
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_with_perimetre():
    """Utilisateur avec un périmètre départemental"""
    collegue = CollegueFactory()
    perimetre = PerimetreDepartementalFactory()
    collegue.perimetre = perimetre
    collegue.save()
    return collegue


class TestProgrammationProjetListView:
    def test_list_view_requires_login(self):
        """La vue liste nécessite une authentification"""
        url = reverse("gsl_programmation:programmation-projet-list")
        response = Client().get(url)
        assert response.status_code == 302  # Redirection vers login

    def test_list_view_with_authenticated_user(self, user_with_perimetre):
        """Un utilisateur authentifié peut accéder à la liste"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        DetrEnveloppeFactory(perimetre=user_with_perimetre.perimetre, annee=2024)
        url = reverse("gsl_programmation:programmation-projet-list")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )


class TestProgrammationProjetListViewWithDotation:
    @pytest.fixture
    def dsil_programmation_projet(self, user_with_perimetre):
        dsil_enveloppe = DsilEnveloppeFactory(
            perimetre=user_with_perimetre.perimetre.parent,
            annee=2024,  # DSIL programmation can only be on Region
        )
        return ProgrammationProjetFactory(
            dotation_projet__projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            enveloppe=dsil_enveloppe,
        )

    @pytest.fixture
    def detr_programmation_projet(self, user_with_perimetre):
        detr_enveloppe = DetrEnveloppeFactory(
            perimetre=user_with_perimetre.perimetre, annee=2024
        )
        return ProgrammationProjetFactory(
            dotation_projet__projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            enveloppe=detr_enveloppe,
        )

    def test_list_view_with_detr(
        self, user_with_perimetre, detr_programmation_projet, dsil_programmation_projet
    ):
        """Un utilisateur avec un périmètre peut accéder à la liste des projets"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert "programmation_projets" in response.context
        assert response.context["programmation_projets"].count() == 1
        assert (
            response.context["programmation_projets"].first()
            == detr_programmation_projet
        )

    def test_list_view_with_dsil(
        self, user_with_perimetre, detr_programmation_projet, dsil_programmation_projet
    ):
        """Un utilisateur avec un périmètre peut accéder à la liste des projets DSIL"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DSIL"},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert "programmation_projets" in response.context
        assert response.context["programmation_projets"].count() == 1
        assert (
            response.context["programmation_projets"].first()
            == dsil_programmation_projet
        )

    def test_list_view_renders_import_documents_button(
        self, user_with_perimetre, detr_programmation_projet
    ):
        """La barre d'outils propose l'import des documents signés."""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        response = client.get(url)
        content = response.content.decode()
        assert "Importer les documents signés" in content
        assert (
            reverse(
                "gsl_notification:import-documents-modal", kwargs={"dotation": "DETR"}
            )
            in content
        )

    @pytest.fixture
    def user_with_regional_perimetre(self):
        """Utilisateur avec un périmètre régional"""
        collegue = CollegueFactory()
        perimetre = PerimetreRegionalFactory()
        collegue.perimetre = perimetre
        collegue.save()
        return collegue

    def test_list_view_with_regional_user_redirect_detr_to_dsil(
        self, user_with_regional_perimetre
    ):
        """Un utilisateur avec un périmètre régional est rediriger d'office vers la liste DSIL"""
        client = ClientWithLoggedUserFactory(user=user_with_regional_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DSIL"},
        )


class TestProgrammationProjetListViewExcludesInactiveDossiers:
    def test_list_view_excludes_projets_with_inactive_dossier(
        self, user_with_perimetre
    ):
        detr_enveloppe = DetrEnveloppeFactory(
            perimetre=user_with_perimetre.perimetre, annee=2024
        )
        active_pp = ProgrammationProjetFactory(
            dotation_projet__projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            enveloppe=detr_enveloppe,
        )
        ProgrammationProjetFactory(
            dotation_projet__projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            dotation_projet__projet__dossier_ds__is_active=False,
            enveloppe=detr_enveloppe,
        )

        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        response = client.get(url)

        assert response.status_code == 200
        programmation_projets = response.context["programmation_projets"]
        assert programmation_projets.count() == 1
        assert programmation_projets.first() == active_pp
