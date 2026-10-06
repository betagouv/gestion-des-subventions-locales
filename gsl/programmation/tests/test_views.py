import pytest
from django.test import Client
from django.urls import reverse

from gsl.core.campagne import default_campagne
from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
)
from gsl.programmation.tests.factories import (
    DetrEnveloppeFactory,
    DsilEnveloppeFactory,
)
from gsl.projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    ProjetStatus,
)
from gsl.projet.tests.factories import EnveloppeProjetFactory

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
        url = reverse(
            "gsl_programmation:programmation-projet-list",
            kwargs={"campagne": default_campagne()},
        )
        response = Client().get(url)
        assert response.status_code == 302  # Redirection vers login

    def test_list_view_with_authenticated_user(self, user_with_perimetre):
        """Un utilisateur authentifié peut accéder à la liste"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        DetrEnveloppeFactory(perimetre=user_with_perimetre.perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list",
            kwargs={"campagne": default_campagne()},
        )
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR", "campagne": default_campagne()},
        )


class TestProgrammationProjetListViewWithDotation:
    @pytest.fixture
    def dsil_enveloppe_projet(self, user_with_perimetre):
        dsil_enveloppe = DsilEnveloppeFactory(
            perimetre=user_with_perimetre.perimetre.parent,
            # DSIL programmation can only be on Region
        )
        return EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            dotation=DOTATION_DSIL,
            status=ProjetStatus.ACCEPTED,
            enveloppe=dsil_enveloppe,
        )

    @pytest.fixture
    def detr_enveloppe_projet(self, user_with_perimetre):
        detr_enveloppe = DetrEnveloppeFactory(perimetre=user_with_perimetre.perimetre)
        return EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            enveloppe=detr_enveloppe,
        )

    def test_list_view_with_detr(
        self, user_with_perimetre, detr_enveloppe_projet, dsil_enveloppe_projet
    ):
        """Un utilisateur avec un périmètre peut accéder à la liste des projets"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR", "campagne": default_campagne()},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert "enveloppe_projets" in response.context
        assert response.context["enveloppe_projets"].count() == 1
        assert response.context["enveloppe_projets"].first() == detr_enveloppe_projet

    def test_list_view_with_dsil(
        self, user_with_perimetre, detr_enveloppe_projet, dsil_enveloppe_projet
    ):
        """Un utilisateur avec un périmètre peut accéder à la liste des projets DSIL"""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DSIL", "campagne": default_campagne()},
        )
        response = client.get(url)
        assert response.status_code == 200
        assert "enveloppe_projets" in response.context
        assert response.context["enveloppe_projets"].count() == 1
        assert response.context["enveloppe_projets"].first() == dsil_enveloppe_projet

    def test_list_view_renders_import_documents_button(
        self, user_with_perimetre, detr_enveloppe_projet
    ):
        """La barre d'outils propose l'import des documents signés."""
        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR", "campagne": default_campagne()},
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
            kwargs={"dotation": "DETR", "campagne": default_campagne()},
        )
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DSIL", "campagne": default_campagne()},
        )


class TestProgrammationProjetListViewContent:
    """
    La liste de programmation affiche les EnveloppeProjet *traités* (acceptés,
    refusés ou classés sans suite) de l'enveloppe de l'utilisateur :
    - enveloppe racine : ceux programmés sur cette enveloppe ;
    - enveloppe déléguée : ceux programmés sur l'enveloppe mère (même dotation),
      restreints au périmètre de l'enveloppe déléguée.

    N'y figurent jamais :
    - les EnveloppeProjet encore en traitement, même lorsque le projet est en
      double dotation et que l'autre dotation est traitée ;
    - les EnveloppeProjet hors du périmètre de l'enveloppe de l'utilisateur.
    """

    @pytest.fixture
    def perimetre_departement(self):
        return PerimetreDepartementalFactory()

    @pytest.fixture
    def perimetre_arrondissement(self, perimetre_departement):
        return PerimetreArrondissementFactory(
            arrondissement__departement=perimetre_departement.departement
        )

    @pytest.fixture
    def perimetre_autre_arrondissement(self, perimetre_departement):
        return PerimetreArrondissementFactory(
            arrondissement__departement=perimetre_departement.departement
        )

    @pytest.fixture
    def enveloppe_racine(self, perimetre_departement):
        return DetrEnveloppeFactory(perimetre=perimetre_departement)

    @pytest.fixture
    def enveloppe_deleguee(self, perimetre_arrondissement, enveloppe_racine):
        enveloppe = DetrEnveloppeFactory(perimetre=perimetre_arrondissement)
        assert enveloppe.parent == enveloppe_racine
        return enveloppe

    def _get_enveloppe_projets(self, perimetre):
        client = ClientWithLoggedUserFactory(user=CollegueFactory(perimetre=perimetre))
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": DOTATION_DETR, "campagne": default_campagne()},
        )
        response = client.get(url)
        assert response.status_code == 200
        return set(response.context["enveloppe_projets"])

    # --- Enveloppe racine ---

    @pytest.mark.parametrize("status", ProjetStatus.FINAL)
    def test_enveloppe_racine_affiche_les_ep_traites(
        self, status, perimetre_arrondissement, enveloppe_racine
    ):
        enveloppe_projet = EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            dotation=DOTATION_DETR,
            status=status,
            enveloppe=enveloppe_racine,
        )

        assert self._get_enveloppe_projets(enveloppe_racine.perimetre) == {
            enveloppe_projet
        }

    def test_enveloppe_racine_n_affiche_pas_les_ep_en_traitement(
        self, perimetre_arrondissement, enveloppe_racine
    ):
        EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            dotation=DOTATION_DETR,
            status=ProjetStatus.PROCESSING,
            enveloppe=enveloppe_racine,
        )

        assert self._get_enveloppe_projets(enveloppe_racine.perimetre) == set()

    def test_enveloppe_racine_n_affiche_pas_l_ep_en_traitement_d_un_projet_double_dotation_dont_l_autre_dotation_est_traitee(
        self, perimetre_arrondissement, enveloppe_racine
    ):
        detr_enveloppe_projet = EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            dotation=DOTATION_DETR,
            status=ProjetStatus.PROCESSING,
            enveloppe=enveloppe_racine,
        )
        EnveloppeProjetFactory(
            projet=detr_enveloppe_projet.projet,
            dotation=DOTATION_DSIL,
            status=ProjetStatus.ACCEPTED,
        )

        assert self._get_enveloppe_projets(enveloppe_racine.perimetre) == set()

    # --- Enveloppe déléguée ---

    @pytest.mark.parametrize("status", ProjetStatus.FINAL)
    def test_enveloppe_deleguee_affiche_les_ep_traites_de_l_enveloppe_mere_dans_son_perimetre(
        self, status, perimetre_arrondissement, enveloppe_racine, enveloppe_deleguee
    ):
        enveloppe_projet = EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            dotation=DOTATION_DETR,
            status=status,
            enveloppe=enveloppe_racine,
        )

        assert self._get_enveloppe_projets(enveloppe_deleguee.perimetre) == {
            enveloppe_projet
        }

    def test_enveloppe_deleguee_n_affiche_pas_les_ep_hors_de_son_perimetre(
        self, perimetre_autre_arrondissement, enveloppe_racine, enveloppe_deleguee
    ):
        EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=perimetre_autre_arrondissement,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            enveloppe=enveloppe_racine,
        )

        assert self._get_enveloppe_projets(enveloppe_deleguee.perimetre) == set()

    def test_enveloppe_deleguee_n_affiche_pas_les_ep_en_traitement(
        self, perimetre_arrondissement, enveloppe_racine, enveloppe_deleguee
    ):
        EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=perimetre_arrondissement,
            dotation=DOTATION_DETR,
            status=ProjetStatus.PROCESSING,
            enveloppe=enveloppe_racine,
        )

        assert self._get_enveloppe_projets(enveloppe_deleguee.perimetre) == set()


class TestProgrammationProjetListViewExcludesInactiveDossiers:
    def test_list_view_excludes_projets_with_inactive_dossier(
        self, user_with_perimetre
    ):
        detr_enveloppe = DetrEnveloppeFactory(perimetre=user_with_perimetre.perimetre)
        active_enveloppe_projet = EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            enveloppe=detr_enveloppe,
        )
        EnveloppeProjetFactory(
            projet__dossier_ds__perimetre=user_with_perimetre.perimetre,
            projet__dossier_ds__is_active=False,
            dotation=DOTATION_DETR,
            status=ProjetStatus.ACCEPTED,
            enveloppe=detr_enveloppe,
        )

        client = ClientWithLoggedUserFactory(user=user_with_perimetre)
        url = reverse(
            "gsl_programmation:programmation-projet-list-dotation",
            kwargs={"dotation": "DETR", "campagne": default_campagne()},
        )
        response = client.get(url)

        assert response.status_code == 200
        enveloppe_projets = response.context["enveloppe_projets"]
        assert enveloppe_projets.count() == 1
        assert enveloppe_projets.first() == active_enveloppe_projet
