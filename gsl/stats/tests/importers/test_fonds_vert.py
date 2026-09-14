import pytest
import responses

from gsl_core.api.fonds_vert import FONDS_VERT_BASE_URL

from ...importers.fonds_vert import (
    FONDS_VERT_DISPOSITIF,
    FONDS_VERT_PROGRAMME,
    _import_fonds_vert_dossier,
    _import_fonds_vert_page,
    import_fonds_vert_subventions,
)
from ...models import FondsVertImportState, Subvention

pytestmark = pytest.mark.django_db

LOGIN_URL = f"{FONDS_VERT_BASE_URL}/fonds_vert/login"
DOSSIERS_URL = f"{FONDS_VERT_BASE_URL}/fonds_vert/v2/dossiers"


def _fonds_vert_item(**socle_commun_overrides):
    socle_commun = {
        "dossier_number": 42,
        "siret": "21750056900011",
        "annee_millesime": 2026,
        "nom_du_projet": "Isolation mairie",
        "statut": "En instruction",
        "montant_aide_demandee_fond_vert": 200,
        "montant_subvention_attribuee": None,
        "total_des_depenses": 400,
    }
    socle_commun.update(socle_commun_overrides)
    return {"socle_commun": socle_commun}


class TestImportFondsVertDossier:
    def _item(self, **socle_commun_overrides):
        return _fonds_vert_item(**socle_commun_overrides)

    def test_creates_a_fonds_vert_subvention(self):
        created = _import_fonds_vert_dossier(self._item())

        assert created is True
        subvention = Subvention.objects.get(dossier_number=42)
        assert subvention.source == Subvention.SOURCE_FONDS_VERT
        assert subvention.siren == "217500569"
        assert subvention.exercice == 2026
        assert subvention.dispositif == FONDS_VERT_DISPOSITIF
        assert subvention.programme == FONDS_VERT_PROGRAMME
        assert subvention.intitule == "Isolation mairie"
        assert subvention.status == "en_instruction"
        assert subvention.montant_demande == 200
        assert subvention.montant_attribue is None
        assert subvention.cout_total == 400

    def test_upserts_by_dossier_number_instead_of_duplicating(self):
        assert _import_fonds_vert_dossier(self._item()) is True

        updated = _import_fonds_vert_dossier(
            self._item(montant_subvention_attribuee=150, statut="Accepté")
        )

        assert updated is False
        assert Subvention.objects.filter(dossier_number=42).count() == 1
        subvention = Subvention.objects.get(dossier_number=42)
        assert subvention.montant_attribue == 150
        assert subvention.status == "accepte"

    def test_two_distinct_dossiers_with_same_siren_and_blank_intitule_are_both_kept(
        self,
    ):
        # Reproduit le bug corrigé par la contrainte unique scopée à la DGCL :
        # deux dossiers Fonds Vert distincts d'un même siren/exercice, tous
        # deux sans intitulé, ne doivent pas entrer en collision.
        first = self._item(dossier_number=1, nom_du_projet="")
        second = self._item(dossier_number=2, nom_du_projet="")

        assert _import_fonds_vert_dossier(first) is True
        assert _import_fonds_vert_dossier(second) is True
        assert Subvention.objects.filter(siren="217500569").count() == 2

    @pytest.mark.parametrize("missing_field", ["dossier_number", "siret"])
    def test_skips_dossier_missing_a_required_field(self, missing_field):
        item = self._item(**{missing_field: None})

        assert _import_fonds_vert_dossier(item) is False
        assert not Subvention.objects.exists()


class TestImportFondsVertPage:
    """`_import_fonds_vert_page` traite une page brute (cf.
    `gsl_core.api.fonds_vert.iter_dossiers_pages`)."""

    def test_reports_created_and_updated_counts(self):
        first = _fonds_vert_item(dossier_number=1)
        second = _fonds_vert_item(dossier_number=2)

        created, updated, errors = _import_fonds_vert_page([first, second])

        assert created == 2
        assert updated == 0
        assert errors == []
        assert Subvention.objects.count() == 2

        # Réimporter la même page : les deux dossiers sont mis à jour, pas dupliqués.
        created, updated, errors = _import_fonds_vert_page([first, second])

        assert created == 0
        assert updated == 2
        assert Subvention.objects.count() == 2

    def test_reports_errors_without_stopping_the_page(self):
        good = _fonds_vert_item(dossier_number=1)
        # siret non-string : fait planter le `.strip()` dans _import_fonds_vert_dossier.
        bad = _fonds_vert_item(dossier_number=99, siret=12345678901234)

        created, updated, errors = _import_fonds_vert_page([bad, good])

        assert created == 1
        assert updated == 0
        assert len(errors) == 1
        assert errors[0]["dossier_number"] == 99
        assert Subvention.objects.filter(dossier_number=1).exists()
        assert not Subvention.objects.filter(dossier_number=99).exists()


class TestImportFondsVertSubventions:
    """`import_fonds_vert_subventions` : connexion (cf.
    `gsl_core.api.fonds_vert`) + curseur de reprise (`FondsVertImportState`)."""

    @pytest.fixture(autouse=True)
    def fonds_vert_credentials(self, settings):
        settings.FONDS_VERT_USERNAME = "user"
        settings.FONDS_VERT_PASSWORD = "pass"

    def _mock_login(self):
        responses.add(responses.POST, LOGIN_URL, json={"access_token": "tok"})

    def _mock_one_page(self):
        responses.add(
            responses.GET,
            DOSSIERS_URL,
            json={"data": [_fonds_vert_item(dossier_number=1)], "next_page": None},
        )

    @responses.activate
    def test_resumes_from_the_saved_cursor_by_default(self):
        state = FondsVertImportState.load()
        state.data["last_page"] = 3
        state.save(update_fields=["data", "updated_at"])
        self._mock_login()
        self._mock_one_page()

        import_fonds_vert_subventions()

        assert responses.calls[1].request.params["page"] == "4"

    @responses.activate
    def test_restart_ignores_the_saved_cursor(self):
        state = FondsVertImportState.load()
        state.data["last_page"] = 3
        state.save(update_fields=["data", "updated_at"])
        self._mock_login()
        self._mock_one_page()

        import_fonds_vert_subventions(restart=True)

        assert responses.calls[1].request.params["page"] == "1"

    @responses.activate
    def test_resets_the_cursor_once_the_sync_is_complete(self):
        self._mock_login()
        self._mock_one_page()

        import_fonds_vert_subventions()

        assert FondsVertImportState.load().data["last_page"] == 0

    def test_returns_an_empty_bilan_when_credentials_are_missing(self, settings):
        settings.FONDS_VERT_USERNAME = ""

        assert import_fonds_vert_subventions() == {}
