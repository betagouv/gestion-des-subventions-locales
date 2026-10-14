import pytest
from django.urls import reverse

from gsl.core.tests.factories import (
    ClientWithLoggedUserFactory,
    CollegueFactory,
    CommuneFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def departement():
    return DepartementFactory(insee_code="75")


@pytest.fixture
def staff_client(departement):
    user = CollegueFactory(
        is_staff=True, perimetre=PerimetreDepartementalFactory(departement=departement)
    )
    return ClientWithLoggedUserFactory(user)


class TestCollectiviteFicoView:
    def test_menu_lists_the_communes_of_the_perimetre(self, staff_client, departement):
        CommuneFactory(departement=departement, name="Bourg", siren="222222222")
        CommuneFactory(departement=departement, name="Aubry", siren="111111111")
        CommuneFactory(departement=departement, name="Sans SIREN", siren="")
        ailleurs = DepartementFactory(insee_code="69")
        CommuneFactory(departement=ailleurs, name="Hors périmètre", siren="333333333")

        response = staff_client.get(reverse("suivi_financier:collectivite-fico"))

        assert response.status_code == 200
        collectivites = list(response.context["collectivites"])
        assert [c.name for c in collectivites] == ["Aubry", "Bourg"]
        assert "<fico-fiche" not in response.content.decode()

    def test_redirects_to_the_chosen_collectivite(self, staff_client):
        response = staff_client.get(
            reverse("suivi_financier:collectivite-fico"), {"siren": "111111111"}
        )

        assert response.status_code == 302
        assert response.url == reverse(
            "suivi_financier:collectivite-fico", args=["111111111"]
        )

    def test_embeds_the_fiche_and_its_pdf(self, staff_client, settings):
        settings.FICO_URL = "https://fico.example"

        response = staff_client.get(
            reverse("suivi_financier:collectivite-fico", args=["111111111"])
        )

        html = response.content.decode()
        fiche = "https://fico.example/fiches/111111111"
        assert f'<fico-fiche src="{fiche}.json?component=' in html
        assert f'href="{fiche}.pdf?component=' in html
