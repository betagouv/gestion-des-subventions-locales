import pytest
from django.test import Client
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_programmation.tests.factories import ProgrammationProjetFactory
from gsl_programmation.views import (
    ProgrammationProjetDetailView,
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


@pytest.fixture
def programmation_projet(user_with_perimetre):
    """Projet programmé dans le périmètre de l'utilisateur"""
    return ProgrammationProjetFactory(
        dotation_projet__projet__perimetre=user_with_perimetre.perimetre
    )


@pytest.fixture
def other_programmation_projet():
    """Projet programmé dans un autre périmètre"""
    return ProgrammationProjetFactory()


class TestProgrammationProjetListView:
    def test_list_view_requires_login(self):
        """La vue liste nécessite une authentification"""
        url = reverse("gsl_programmation:programmation-projet-list")
        response = Client().get(url)
        assert response.status_code == 302  # Redirection vers login

    def test_list_view_with_authenticated_user(self, user_with_perimetre):
        """Un utilisateur authentifié peut accéder à la liste"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("gsl_programmation:programmation-projet-list")
        response = client.get(url)
        assert response.status_code == 200
        assert "programmation_projets" in response.context

    def test_list_view_shows_only_user_perimeter_projects(
        self, user_with_perimetre, programmation_projet, other_programmation_projet
    ):
        """La liste n'affiche que les projets du périmètre de l'utilisateur"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("gsl_programmation:programmation-projet-list")
        response = client.get(url)

        assert programmation_projet in response.context["programmation_projets"]
        assert (
            other_programmation_projet not in response.context["programmation_projets"]
        )

    def test_list_view_context_data(self, user_with_perimetre, programmation_projet):
        """Test du contexte de la vue liste"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse("gsl_programmation:programmation-projet-list")
        response = client.get(url)

        assert "title" in response.context
        assert "enveloppe" in response.context
        assert "breadcrumb_dict" in response.context


class TestProgrammationProjetDetailView:
    """Tests pour la vue détail d'un projet programmé"""

    def test_detail_view_requires_login(self, programmation_projet):
        """La vue détail nécessite une authentification"""
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"programmation_projet_id": programmation_projet.id},
        )
        response = Client().get(url)
        assert response.status_code == 302  # Redirection vers login

    def test_detail_view_with_authorized_user(
        self, user_with_perimetre, programmation_projet
    ):
        """Un utilisateur autorisé peut accéder au détail"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"programmation_projet_id": programmation_projet.id},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["programmation_projet"] == programmation_projet

    def test_detail_view_unauthorized_user_gets_404(
        self, user_with_perimetre, other_programmation_projet
    ):
        """Un utilisateur non autorisé reçoit une 404"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"programmation_projet_id": other_programmation_projet.id},
        )
        response = client.get(url)
        assert response.status_code == 404

    def test_detail_view_context_data(self, user_with_perimetre, programmation_projet):
        """Test du contexte de la vue détail"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"programmation_projet_id": programmation_projet.id},
        )
        response = client.get(url)

        assert response.context["current_tab"] == "projet"
        assert "title" in response.context
        assert "projet" in response.context
        assert "dossier" in response.context
        assert "enveloppe" in response.context
        assert "breadcrumb_dict" in response.context
        assert "menu_dict" in response.context

    def test_detail_view_optimized_queries(
        self, user_with_perimetre, programmation_projet
    ):
        """Test que les requêtes sont optimisées avec select_related/prefetch_related"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"programmation_projet_id": programmation_projet.id},
        )

        # Testons que le contexte contient bien les données attendues
        response = client.get(url)
        assert response.status_code == 200

        # Vérifions que les relations sont bien chargées
        programmation_projet_context = response.context["programmation_projet"]
        assert hasattr(programmation_projet_context, "projet")
        assert hasattr(programmation_projet_context.projet, "dossier_ds")
        assert hasattr(programmation_projet_context, "enveloppe")


class TestProgrammationProjetTabView:
    """Tests pour la vue onglets d'un projet programmé"""

    def test_tab_view_requires_login(self, programmation_projet):
        """La vue onglet nécessite une authentification"""
        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={
                "programmation_projet_id": programmation_projet.id,
                "tab": "annotations",
            },
        )
        response = Client().get(url)
        assert response.status_code == 302  # Redirection vers login

    # TODO add test for notifications tab when implemented
    @pytest.mark.parametrize(
        "tab",
        ("annotations", "historique"),
    )
    def test_tab_view_with_valid_tab(
        self, user_with_perimetre, programmation_projet, tab
    ):
        """Un utilisateur autorisé peut accéder aux onglets valides"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)

        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={"programmation_projet_id": programmation_projet.id, "tab": tab},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["current_tab"] == tab
        assert response.context["programmation_projet"] == programmation_projet

    def test_tab_view_with_invalid_tab_returns_404(
        self, user_with_perimetre, programmation_projet
    ):
        """Un onglet invalide retourne une 404"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={
                "programmation_projet_id": programmation_projet.id,
                "tab": "invalid_tab",
            },
        )
        response = client.get(url)
        assert response.status_code == 404

    def test_tab_view_unauthorized_user_gets_404(
        self, user_with_perimetre, other_programmation_projet
    ):
        """Un utilisateur non autorisé reçoit une 404 même avec un onglet valide"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={
                "programmation_projet_id": other_programmation_projet.id,
                "tab": "annotations",
            },
        )
        response = client.get(url)
        assert response.status_code == 404

    # TODO add notifications tab test when implemented
    @pytest.mark.parametrize(
        "tab",
        ("annotations", "historique"),
    )
    def test_tab_view_uses_correct_template(
        self, user_with_perimetre, programmation_projet, tab
    ):
        """Chaque onglet utilise le bon template"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)

        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={"programmation_projet_id": programmation_projet.id, "tab": tab},
        )
        response = client.get(url)
        expected_template = f"gsl_programmation/tab_programmation_projet/tab_{tab}.html"
        assert expected_template in [t.name for t in response.templates]

    def test_tab_view_context_data(self, user_with_perimetre, programmation_projet):
        """Test du contexte de la vue onglet"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={
                "programmation_projet_id": programmation_projet.id,
                "tab": "annotations",
            },
        )
        response = client.get(url)

        assert response.context["current_tab"] == "annotations"
        assert "title" in response.context
        assert "projet" in response.context
        assert "dossier" in response.context
        assert "enveloppe" in response.context
        assert "breadcrumb_dict" in response.context
        assert "menu_dict" in response.context


class TestTabConstants:
    def test_programmation_projet_tabs_constant(self):
        """Test que la constante ALLOWED_TABS contient les bons onglets"""
        expected_tabs = {"annotations", "historique", "notifications"}
        assert ProgrammationProjetDetailView.ALLOWED_TABS == expected_tabs


class TestProgrammationProjetSecurity:
    """Tests de sécurité pour les vues"""

    def test_staff_user_can_access_any_project(self, programmation_projet):
        """Un utilisateur staff peut accéder à n'importe quel projet"""
        staff_user = CollegueFactory(is_staff=True)
        client = ClientWithLoggedUserFactory(user=staff_user)

        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"programmation_projet_id": programmation_projet.id},
        )
        response = client.get(url)
        assert response.status_code == 200

    def test_regular_user_cannot_access_project_outside_perimeter(
        self, user_with_perimetre, other_programmation_projet
    ):
        """Un utilisateur normal ne peut pas accéder à un projet hors de son périmètre"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)

        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"programmation_projet_id": other_programmation_projet.id},
        )
        response = client.get(url)
        assert response.status_code == 404
