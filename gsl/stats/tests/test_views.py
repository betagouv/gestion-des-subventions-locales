import pytest
from django.urls import reverse

from gsl.core.tests.factories import (
    AdresseFactory,
    ClientWithLoggedUserFactory,
    CollegueFactory,
    CommuneFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.tests.factories import PersonneMoraleFactory

pytestmark = pytest.mark.django_db


def _personne_morale(siret, commune, **kwargs):
    return PersonneMoraleFactory(
        siret=siret, address=AdresseFactory(commune=commune), **kwargs
    )


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
    def test_menu_lists_the_perimetre_once_per_siren(self, staff_client, departement):
        commune = CommuneFactory(departement=departement)
        _personne_morale("11111111100011", commune, raison_sociale="Etab A")
        _personne_morale("11111111100022", commune, raison_sociale="Etab B")
        _personne_morale("22222222200011", commune, raison_sociale="Autre entité")
        ailleurs = CommuneFactory(departement=DepartementFactory(insee_code="69"))
        _personne_morale("33333333300011", ailleurs, raison_sociale="Hors périmètre")

        response = staff_client.get(reverse("suivi_financier:collectivite-fico"))

        assert response.status_code == 200
        collectivites = list(response.context["collectivites"])
        assert [c.siren for c in collectivites] == ["222222222", "111111111"]
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
