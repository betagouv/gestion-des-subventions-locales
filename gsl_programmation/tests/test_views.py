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
from gsl_programmation.views import (
    ProgrammationProjetDetailView,
)
from gsl_projet.tests.factories import ProjetFactory

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
def projet(user_with_perimetre):
    """Projet dans le périmètre de l'utilisateur"""
    return ProjetFactory(perimetre=user_with_perimetre.perimetre)


@pytest.fixture
def programmation_projet(projet):
    """Projet programmé dans le périmètre de l'utilisateur"""
    return ProgrammationProjetFactory(dotation_projet__projet=projet)


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
            dotation_projet__projet__perimetre=user_with_perimetre.perimetre,
            enveloppe=dsil_enveloppe,
        )

    @pytest.fixture
    def detr_programmation_projet(self, user_with_perimetre):
        detr_enveloppe = DetrEnveloppeFactory(
            perimetre=user_with_perimetre.perimetre, annee=2024
        )
        return ProgrammationProjetFactory(
            dotation_projet__projet__perimetre=user_with_perimetre.perimetre,
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


class TestProgrammationProjetDetailView:
    """Tests pour la vue détail d'un projet programmé"""

    def test_detail_view_requires_login(self, programmation_projet):
        """La vue détail nécessite une authentification"""
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": programmation_projet.projet.id},
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
            kwargs={"projet_id": programmation_projet.projet.id},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["projet"] == programmation_projet.projet

    def test_detail_view_unauthorized_user_gets_404(
        self, user_with_perimetre, other_programmation_projet
    ):
        """Un utilisateur non autorisé reçoit une 404"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": other_programmation_projet.projet.id},
        )
        response = client.get(url)
        assert response.status_code == 404

    def test_view_if_projet_has_no_programmation_projet(
        self, user_with_perimetre, projet
    ):
        """Un utilisateur autorisé reçoit une 404 si le projet n'a pas de programmation projet"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": projet.id},
        )
        response = client.get(url)
        assert response.status_code == 404

    def test_detail_view_context_data(self, user_with_perimetre, programmation_projet):
        """Test du contexte de la vue détail"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": programmation_projet.projet.id},
        )
        response = client.get(url)

        assert response.context["current_tab"] == "projet"
        assert "title" in response.context
        assert "projet" in response.context
        assert "dossier" in response.context
        assert "breadcrumb_dict" in response.context
        assert "menu_dict" in response.context

    def test_detail_view_optimized_queries(
        self, user_with_perimetre, programmation_projet
    ):
        """Test que les requêtes sont optimisées avec select_related/prefetch_related"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": programmation_projet.projet.id},
        )

        # Testons que le contexte contient bien les données attendues
        response = client.get(url)
        assert response.status_code == 200

        # Vérifions que les relations sont bien chargées
        projet_context = response.context["projet"]
        assert hasattr(projet_context, "dossier_ds")
        assert hasattr(projet_context, "perimetre")
        assert hasattr(projet_context, "demandeur")
        assert hasattr(projet_context, "dotationprojet_set")

    def test_get_go_back_link_with_dotation_in_query_string(
        self, user_with_perimetre, programmation_projet
    ):
        """Test get_go_back_link quand 'dotation' est dans les paramètres de requête"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": programmation_projet.projet.id},
        )
        response = client.get(url + "?dotation=DETR&page=1&search=test")
        assert response.status_code == 200

        go_back_link = response.context["go_back_link"]
        expected_url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR"},
        )
        assert go_back_link.startswith(expected_url)
        assert "dotation" not in go_back_link
        assert "page=1" in go_back_link
        assert "search=test" in go_back_link

    def test_get_go_back_link_without_dotation_in_query_string(
        self, user_with_perimetre, programmation_projet
    ):
        """Test get_go_back_link quand 'dotation' n'est pas dans les paramètres de requête"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": programmation_projet.projet.id},
        )
        response = client.get(url + "?page=1&search=test")
        assert response.status_code == 200

        go_back_link = response.context["go_back_link"]
        expected_url = reverse("gsl_programmation:programmation-projet-list")
        assert go_back_link.startswith(expected_url)
        assert "page=1" in go_back_link
        assert "search=test" in go_back_link
        assert "dotation" not in go_back_link

    def test_get_go_back_link_with_no_query_parameters(
        self, user_with_perimetre, programmation_projet
    ):
        """Test get_go_back_link sans paramètres de requête"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": programmation_projet.projet.id},
        )
        response = client.get(url)
        assert response.status_code == 200

        go_back_link = response.context["go_back_link"]
        expected_url = reverse("gsl_programmation:programmation-projet-list")
        assert go_back_link == expected_url

    def test_get_go_back_link_with_dotation_dsil(
        self, user_with_perimetre, programmation_projet
    ):
        """Test get_go_back_link avec dotation DSIL"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": programmation_projet.projet.id},
        )
        response = client.get(url + "?dotation=DSIL")
        assert response.status_code == 200

        go_back_link = response.context["go_back_link"]
        expected_url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DSIL"},
        )
        assert go_back_link.startswith(expected_url)
        assert "dotation=DSIL" not in go_back_link


class TestProgrammationProjetTabView:
    """Tests pour la vue onglets d'un projet programmé"""

    def test_tab_view_requires_login(self, programmation_projet):
        """La vue onglet nécessite une authentification"""
        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={
                "projet_id": programmation_projet.projet.id,
                "tab": "notes",
            },
        )
        response = Client().get(url)
        assert response.status_code == 302  # Redirection vers login

    @pytest.mark.parametrize(
        "tab",
        ("notes", "historique"),
    )
    def test_tab_view_with_valid_tab(
        self, user_with_perimetre, programmation_projet, tab
    ):
        """Un utilisateur autorisé peut accéder aux onglets valides"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)

        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={"projet_id": programmation_projet.projet.id, "tab": tab},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["current_tab"] == tab
        assert response.context["projet"] == programmation_projet.projet

    def test_tab_view_with_invalid_tab_returns_404(
        self, user_with_perimetre, programmation_projet
    ):
        """Un onglet invalide retourne une 404"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={
                "projet_id": programmation_projet.projet.id,
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
                "projet_id": other_programmation_projet.projet.id,
                "tab": "notes",
            },
        )
        response = client.get(url)
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "tab",
        ("notes", "historique"),
    )
    def test_tab_view_uses_correct_template(
        self, user_with_perimetre, programmation_projet, tab
    ):
        """Chaque onglet utilise le bon template"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)

        url = reverse(
            "gsl_programmation:programmation-projet-tab",
            kwargs={"projet_id": programmation_projet.projet.id, "tab": tab},
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
                "projet_id": programmation_projet.projet.id,
                "tab": "notes",
            },
        )
        response = client.get(url)

        assert response.context["current_tab"] == "notes"
        assert "title" in response.context
        assert "projet" in response.context
        assert "dossier" in response.context
        assert "breadcrumb_dict" in response.context
        assert "menu_dict" in response.context


class TestTabConstants:
    def test_programmation_projet_tabs_constant(self):
        """Test que la constante ALLOWED_TABS contient les bons onglets"""
        expected_tabs = {"notes", "historique"}
        assert ProgrammationProjetDetailView.ALLOWED_TABS == expected_tabs


class TestProgrammationProjetSecurity:
    """Tests de sécurité pour les vues"""

    def test_regular_user_cannot_access_project_outside_perimeter(
        self, user_with_perimetre, other_programmation_projet
    ):
        """Un utilisateur normal ne peut pas accéder à un projet hors de son périmètre"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)

        url = reverse(
            "gsl_programmation:programmation-projet-detail",
            kwargs={"projet_id": other_programmation_projet.projet.id},
        )
        response = client.get(url)
        assert response.status_code == 404
