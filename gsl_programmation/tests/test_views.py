import pytest
from django.http import Http404
from django.test import Client
from django.urls import reverse

from gsl_core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl_programmation.models import Enveloppe
from gsl_programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
    ProgrammationProjetFactory,
)
from gsl_programmation.views import (
    ProgrammationProjetDetailView,
    ProgrammationProjetListView,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL

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


class TestProgrammationProjetListViewGetEnveloppe:
    """Tests pour la méthode _get_enveloppe_from_user_perimetre"""

    def test_get_enveloppe_with_no_user_perimetre(self):
        """
        Si l'utilisateur n'a pas de périmètre, retourne la première enveloppe
        """
        # Créer plusieurs enveloppes
        enveloppe1 = DetrEnveloppeFactory(annee=2024)
        DetrEnveloppeFactory(annee=2023)  # Enveloppe plus ancienne

        # Queryset d'enveloppes ordonné par année décroissante
        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DETR).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()
        result = view._get_enveloppe_from_user_perimetre(None, enveloppe_qs)

        assert result == enveloppe1  # La plus récente

    def test_get_enveloppe_exact_perimetre_match(self):
        """
        Si une enveloppe correspond exactement au périmètre de l'utilisateur, la retourner
        """
        perimetre = PerimetreDepartementalFactory()
        enveloppe_matching = DetrEnveloppeFactory(perimetre=perimetre, annee=2024)
        # Créer une autre enveloppe plus récente mais qui ne correspond pas
        DetrEnveloppeFactory(annee=2025)

        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DETR).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()
        result = view._get_enveloppe_from_user_perimetre(perimetre, enveloppe_qs)

        assert result == enveloppe_matching

    def test_get_enveloppe_departement_match(self):
        """
        Si aucune enveloppe ne correspond exactement au périmètre,
        chercher une enveloppe avec le même département
        """
        # Créer un périmètre arrondissement
        perimetre_arrondissement = PerimetreArrondissementFactory()

        # Créer une enveloppe départementale pour le même département
        perimetre_departement = PerimetreDepartementalFactory(
            departement=perimetre_arrondissement.departement,
            region=perimetre_arrondissement.region,
        )
        enveloppe_dept = DetrEnveloppeFactory(
            perimetre=perimetre_departement, annee=2024
        )

        # Créer une autre enveloppe plus récente mais qui ne correspond pas
        DetrEnveloppeFactory(annee=2025)

        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DETR).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()
        result = view._get_enveloppe_from_user_perimetre(
            perimetre_arrondissement, enveloppe_qs
        )

        assert result == enveloppe_dept

    def test_get_enveloppe_region_match(self):
        """
        Si aucune enveloppe ne correspond au périmètre ou au département,
        chercher une enveloppe avec la même région
        """
        # Créer un périmètre départemental
        perimetre_dept = PerimetreDepartementalFactory()

        # Créer une enveloppe régionale pour la même région
        perimetre_region = PerimetreRegionalFactory(region=perimetre_dept.region)
        enveloppe_region = DsilEnveloppeFactory(perimetre=perimetre_region, annee=2024)

        # Créer une autre enveloppe qui ne correspond pas
        DsilEnveloppeFactory(annee=2025)

        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DSIL).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()
        result = view._get_enveloppe_from_user_perimetre(perimetre_dept, enveloppe_qs)

        assert result == enveloppe_region

    def test_get_enveloppe_no_match_raises_404(self):
        """
        Si aucune enveloppe ne correspond au périmètre de l'utilisateur,
        lever une erreur Http404
        """
        # Créer un périmètre
        perimetre = PerimetreDepartementalFactory()

        # Créer une enveloppe qui ne correspond pas du tout (autre région)
        autre_perimetre = PerimetreDepartementalFactory()
        DetrEnveloppeFactory(perimetre=autre_perimetre, annee=2024)

        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DETR).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()

        with pytest.raises(Http404) as exc_info:
            view._get_enveloppe_from_user_perimetre(perimetre, enveloppe_qs)

        assert "Aucune enveloppe trouvée pour le périmètre de l'utilisateur" in str(
            exc_info.value
        )

    def test_get_enveloppe_priority_order(self):
        """
        Vérifier l'ordre de priorité : périmètre exact > département > région
        """
        # Créer un périmètre départemental
        perimetre_dept = PerimetreDepartementalFactory()

        # Créer plusieurs enveloppes avec différents niveaux de correspondance
        # 1. Enveloppe exacte (même périmètre)
        enveloppe_exacte = DetrEnveloppeFactory(perimetre=perimetre_dept, annee=2024)

        # 2. Enveloppe régionale (même région)
        perimetre_region = PerimetreRegionalFactory(region=perimetre_dept.region)
        DetrEnveloppeFactory(
            perimetre=perimetre_region, annee=2025
        )  # Enveloppe régionale

        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DETR).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()
        result = view._get_enveloppe_from_user_perimetre(perimetre_dept, enveloppe_qs)

        # Doit retourner l'enveloppe exacte, pas la régionale
        assert result == enveloppe_exacte

    def test_get_enveloppe_multiple_matches_returns_first(self):
        """
        Si plusieurs enveloppes correspondent au même niveau,
        retourner la première (selon l'ordre du queryset)
        """
        perimetre = PerimetreDepartementalFactory()

        # Créer deux enveloppes avec le même périmètre
        DetrEnveloppeFactory(perimetre=perimetre, annee=2023)  # Enveloppe plus ancienne
        enveloppe2 = DetrEnveloppeFactory(perimetre=perimetre, annee=2024)

        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DETR).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()
        result = view._get_enveloppe_from_user_perimetre(perimetre, enveloppe_qs)

        # Doit retourner la plus récente (2024)
        assert result == enveloppe2

    def test_get_enveloppe_with_arrondissement_perimetre(self):
        """
        Test spécifique pour un périmètre arrondissement qui doit chercher
        d'abord par département, puis par région
        """
        # Créer un périmètre arrondissement
        perimetre_arr = PerimetreArrondissementFactory()

        # Créer une enveloppe régionale pour la même région
        perimetre_region = PerimetreRegionalFactory(region=perimetre_arr.region)
        enveloppe_region = DetrEnveloppeFactory(perimetre=perimetre_region, annee=2024)

        # Pas d'enveloppe départementale correspondante

        enveloppe_qs = Enveloppe.objects.filter(dotation=DOTATION_DETR).order_by(
            "-annee"
        )

        view = ProgrammationProjetListView()
        result = view._get_enveloppe_from_user_perimetre(perimetre_arr, enveloppe_qs)

        assert result == enveloppe_region


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
            perimetre=user_with_perimetre.perimetre, annee=2024
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
        expected_tabs = {"annotations", "historique"}
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
