import json

import pytest
from django.urls import reverse

from gsl.core.tests.factories import (
    ArrondissementFactory,
    ClientWithLoggedUserFactory,
    CollegueFactory,
    CommuneFactory,
    DepartementFactory,
    PerimetreArrondissementFactory,
    PerimetreDepartementalFactory,
    PerimetreRegionalFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fico_url(settings):
    settings.FICO_URL = "https://fico.example"


@pytest.fixture
def departement():
    return DepartementFactory(insee_code="75")


@pytest.fixture
def staff_client(departement):
    user = CollegueFactory(
        is_staff=True, perimetre=PerimetreDepartementalFactory(departement=departement)
    )
    return ClientWithLoggedUserFactory(user)


def _client_for(perimetre):
    return ClientWithLoggedUserFactory(
        CollegueFactory(is_staff=True, perimetre=perimetre)
    )


class TestCollectiviteFicoView:
    def test_menu_queries_the_departement(self, staff_client):
        response = staff_client.get(reverse("suivi_financier:collectivite-fico"))

        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-collectivite-menu-query-value="codeDepartement=75"' in html
        assert "data-collectivite-menu-communes-value" not in html
        assert "<fico-fiche" not in html

    def test_menu_queries_the_region(self):
        perimetre = PerimetreRegionalFactory(region=RegionFactory(insee_code="44"))

        response = _client_for(perimetre).get(
            reverse("suivi_financier:collectivite-fico")
        )

        html = response.content.decode()
        assert 'data-collectivite-menu-query-value="codeRegion=44"' in html

    def test_menu_restricts_to_the_communes_of_the_arrondissement(self, departement):
        arrondissement = ArrondissementFactory(departement=departement)
        CommuneFactory(insee_code="75101", arrondissement=arrondissement)
        CommuneFactory(insee_code="75102", arrondissement=arrondissement)
        CommuneFactory(
            insee_code="75103",
            arrondissement=ArrondissementFactory(departement=departement),
        )
        perimetre = PerimetreArrondissementFactory(arrondissement=arrondissement)

        response = _client_for(perimetre).get(
            reverse("suivi_financier:collectivite-fico")
        )

        html = response.content.decode()
        assert 'data-collectivite-menu-query-value="codeDepartement=75"' in html
        communes = json.loads(response.context["arrondissement_communes"])
        assert sorted(communes) == ["75101", "75102"]

    def test_redirects_to_the_chosen_collectivite(self, staff_client):
        response = staff_client.get(
            reverse("suivi_financier:collectivite-fico"), {"siren": "111111111"}
        )

        assert response.status_code == 302
        assert response.url == reverse(
            "suivi_financier:collectivite-fico", args=["111111111"]
        )

    def test_embeds_the_fiche_and_its_pdf(self, staff_client):
        response = staff_client.get(
            reverse("suivi_financier:collectivite-fico", args=["111111111"])
        )

        html = response.content.decode()
        assert '<fico-fiche collectivite="111111111" components="identite,' in html
        assert 'href="https://fico.example/fiches/111111111.pdf?component=' in html
