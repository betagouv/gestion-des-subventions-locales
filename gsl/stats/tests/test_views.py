import pytest
from django.urls import reverse

from gsl.projet.constants import DS_STATE_ACCEPTE, DS_STATE_EN_INSTRUCTION
from gsl.stats.models import Subvention
from gsl_core.tests.factories import (
    AdresseFactory,
    ClientWithLoggedUserFactory,
    CollegueFactory,
    CommuneFactory,
    DepartementFactory,
    PerimetreDepartementalFactory,
)
from gsl_demarches_simplifiees.tests.factories import PersonneMoraleFactory

pytestmark = pytest.mark.django_db


def _personne_morale(siret, **kwargs):
    return PersonneMoraleFactory(siret=siret, **kwargs)


class TestCollectiviteListView:
    def test_keeps_only_one_personne_morale_per_siren(self):
        _personne_morale("11111111100011", raison_sociale="Etab A")
        _personne_morale("11111111100022", raison_sociale="Etab B")
        _personne_morale("22222222200011", raison_sociale="Autre entité")

        client = ClientWithLoggedUserFactory(CollegueFactory(is_staff=True))
        response = client.get(reverse("suivi_financier:collectivite-list"))

        collectivites = list(response.context["collectivites"])
        assert len(collectivites) == 2
        assert [c.siren for c in collectivites] == ["222222222", "111111111"]
        assert collectivites[1].siret == "11111111100011"

    def test_search_filters_by_nom_or_siren(self):
        _personne_morale("11111111100011", raison_sociale="Ville de Paris")
        _personne_morale("22222222200011", raison_sociale="Ville de Lyon")

        client = ClientWithLoggedUserFactory(CollegueFactory(is_staff=True))
        response = client.get(
            reverse("suivi_financier:collectivite-list"), {"q": "Paris"}
        )

        collectivites = list(response.context["collectivites"])
        assert len(collectivites) == 1
        assert collectivites[0].raison_sociale == "Ville de Paris"

    def test_non_staff_user_only_sees_personnes_morales_in_their_departement(self):
        dep_in = DepartementFactory(insee_code="75")
        dep_out = DepartementFactory(insee_code="69")
        commune_in = CommuneFactory(departement=dep_in)
        commune_out = CommuneFactory(departement=dep_out)

        _personne_morale(
            "11111111100011",
            raison_sociale="Dans le périmètre",
            address=AdresseFactory(commune=commune_in),
        )
        _personne_morale(
            "22222222200011",
            raison_sociale="Hors périmètre",
            address=AdresseFactory(commune=commune_out),
        )

        user = CollegueFactory(
            perimetre=PerimetreDepartementalFactory(departement=dep_in)
        )
        client = ClientWithLoggedUserFactory(user)
        response = client.get(reverse("suivi_financier:collectivite-list"))

        collectivites = list(response.context["collectivites"])
        assert [c.raison_sociale for c in collectivites] == ["Dans le périmètre"]


class TestCollectiviteDetailView:
    def test_returns_404_for_a_siren_outside_the_user_perimetre(self):
        dep_in = DepartementFactory(insee_code="75")
        dep_out = DepartementFactory(insee_code="69")
        commune_out = CommuneFactory(departement=dep_out)
        pm = _personne_morale(
            "22222222200011", address=AdresseFactory(commune=commune_out)
        )

        user = CollegueFactory(
            perimetre=PerimetreDepartementalFactory(departement=dep_in)
        )
        client = ClientWithLoggedUserFactory(user)
        response = client.get(
            reverse("suivi_financier:collectivite-detail", args=[pm.siren])
        )

        assert response.status_code == 404

    def test_shows_subventions_from_both_sources(self):
        pm = _personne_morale("21750056900011", raison_sociale="Ville de Paris")
        Subvention.objects.create(
            source=Subvention.SOURCE_DGCL,
            siren=pm.siren,
            exercice=2024,
            dispositif="DETR",
            programme=119,
            intitule="Rénovation école",
            cout_total=1000,
            montant_attribue=500,
        )
        Subvention.objects.create(
            source=Subvention.SOURCE_FONDS_VERT,
            siren=pm.siren,
            exercice=2026,
            dispositif="FONDS VERT",
            programme=380,
            intitule="Isolation mairie",
            status=DS_STATE_EN_INSTRUCTION,
            montant_demande=200,
            cout_total=400,
            dossier_number=42,
        )

        client = ClientWithLoggedUserFactory(CollegueFactory(is_staff=True))
        response = client.get(
            reverse("suivi_financier:collectivite-detail", args=[pm.siren])
        )

        assert response.status_code == 200
        subventions = list(response.context["subventions"])
        assert {s.intitule for s in subventions} == {
            "Rénovation école",
            "Isolation mairie",
        }
        html = response.content.decode()
        assert "Rénovation école" in html
        assert "Isolation mairie" in html
        assert "En instruction" in html

    def test_hides_the_status_badge_when_accepted(self):
        pm = _personne_morale("21750056900011")
        Subvention.objects.create(
            source=Subvention.SOURCE_FONDS_VERT,
            siren=pm.siren,
            exercice=2026,
            dispositif="FONDS VERT",
            programme=380,
            intitule="Isolation mairie",
            status=DS_STATE_ACCEPTE,
            montant_demande=200,
            montant_attribue=200,
            cout_total=400,
            dossier_number=42,
        )

        client = ClientWithLoggedUserFactory(CollegueFactory(is_staff=True))
        response = client.get(
            reverse("suivi_financier:collectivite-detail", args=[pm.siren])
        )

        assert "Accepté" not in response.content.decode()
