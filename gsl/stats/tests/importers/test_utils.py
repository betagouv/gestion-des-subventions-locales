import pytest

from gsl_core.tests.factories import CommuneFactory, DepartementFactory

from ...importers.utils import (
    parse_excel_decimal,
    reset_geo_cache,
    resolve_commune,
    resolve_departement,
)

pytestmark = pytest.mark.django_db


class TestResolveDepartement:
    @pytest.mark.parametrize("code", ["", None])
    def test_returns_none_for_empty_code(self, code):
        assert resolve_departement(code) is None

    def test_resolves_an_exact_match(self):
        departement = DepartementFactory(insee_code="01")

        assert resolve_departement("01") == departement

    def test_resolves_a_dgcl_zero_padded_mainland_code(self):
        # Les CSV DGCL zero-paddent sur 3 caractères (ex. "001") alors que
        # Departement.insee_code utilise 2 caractères pour la métropole.
        departement = DepartementFactory(insee_code="01")

        assert resolve_departement("001") == departement

    def test_resolves_an_overseas_code_already_on_three_characters(self):
        departement = DepartementFactory(insee_code="971")

        assert resolve_departement("971") == departement

    def test_resolves_a_corse_alphanumeric_code(self):
        departement = DepartementFactory(insee_code="2A")

        assert resolve_departement("2A") == departement

    def test_returns_none_when_no_departement_matches(self):
        DepartementFactory(insee_code="01")

        assert resolve_departement("99") is None

    def test_only_queries_the_database_once_across_several_calls(
        self, django_assert_num_queries
    ):
        DepartementFactory(insee_code="01")
        DepartementFactory(insee_code="02")

        with django_assert_num_queries(1):
            assert resolve_departement("01") is not None
            assert resolve_departement("02") is not None
            assert resolve_departement("99") is None


class TestResolveCommune:
    @pytest.mark.parametrize("code_insee", ["", None])
    def test_returns_none_for_empty_code(self, code_insee):
        assert resolve_commune(code_insee) is None

    def test_resolves_an_exact_match(self):
        commune = CommuneFactory(insee_code="75056")

        assert resolve_commune("75056") == commune

    def test_returns_none_when_no_commune_matches(self):
        CommuneFactory(insee_code="75056")

        assert resolve_commune("99999") is None

    def test_resolves_case_insensitively(self):
        # Les départements corses (2A/2B) sont parfois saisis en minuscules
        # dans les imports (ex. FNADT), alors que Commune.insee_code est
        # enregistré en majuscules.
        commune = CommuneFactory(insee_code="2B267")

        assert resolve_commune("2b267") == commune

    def test_only_queries_the_database_once_across_several_calls(
        self, django_assert_num_queries
    ):
        CommuneFactory(insee_code="75056")
        CommuneFactory(insee_code="69123")

        with django_assert_num_queries(1):
            assert resolve_commune("75056") is not None
            assert resolve_commune("69123") is not None
            assert resolve_commune("00000") is None


class TestResetGeoCache:
    def test_departement_cache_reloads_from_the_database_after_reset(self):
        departement = DepartementFactory(insee_code="01")
        assert resolve_departement("01") == departement

        departement.delete()
        reset_geo_cache()

        assert resolve_departement("01") is None

    def test_commune_cache_reloads_from_the_database_after_reset(self):
        commune = CommuneFactory(insee_code="75056")
        assert resolve_commune("75056") == commune

        commune.delete()
        reset_geo_cache()

        assert resolve_commune("75056") is None

    def test_can_be_called_repeatedly_without_a_prior_resolution(self):
        # La fixture autouse l'appelle avant même qu'un cache ait été
        # rempli : ne doit pas planter.
        reset_geo_cache()
        reset_geo_cache()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1000,50", 1000.50),
        ("1 000,50", 1000.50),
        ("1000.50", 1000.50),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_parse_excel_decimal(raw, expected):
    assert parse_excel_decimal(raw) == expected
