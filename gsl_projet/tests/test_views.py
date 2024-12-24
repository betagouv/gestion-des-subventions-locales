import pytest
from django.test import RequestFactory

from gsl_projet.views import ProjetListView


@pytest.mark.django_db
class TestProjetListView:
    def setup_method(self):
        self.request = RequestFactory()
        self.view = ProjetListView()

    @pytest.mark.parametrize(
        "tri_param,expected_ordering",
        [
            ("date_desc", "-dossier_ds__ds_date_depot"),
            ("date_asc", "dossier_ds__ds_date_depot"),
            ("cout_desc", "-dossier_ds__finance_cout_total"),
            ("cout_asc", "dossier_ds__finance_cout_total"),
            ("commune_desc", "-address__commune__name"),
            ("commune_asc", "address__commune__name"),
            (None, None),  # Test valeur par défaut
            ("invalid_value", None),  # Test valeur invalide
        ],
    )
    def test_get_ordering(self, tri_param, expected_ordering):
        """Test que get_ordering retourne le bon ordre selon le paramètre 'tri'"""
        request = self.request.get("/")
        if tri_param is not None:
            request = self.request.get(f"/?tri={tri_param}")

        self.view.request = request

        assert self.view.get_ordering() == expected_ordering

    def test_get_ordering_with_multiple_params(self):
        """Test que get_ordering fonctionne avec d'autres paramètres dans l'URL"""
        request = self.request.get("/?tri=commune_asc&page=2&search=test")
        self.view.request = request

        assert self.view.get_ordering() == "address__commune__name"
