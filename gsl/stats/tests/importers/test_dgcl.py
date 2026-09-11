import pytest
import responses

from gsl_core.tests.factories import CommuneFactory, DepartementFactory

from ...importers.dgcl import (
    DGCL_API_URL,
    _build_dgcl_subvention,
    _parse_decimal,
    _parse_int,
    import_dgcl_subventions,
)
from ...models import Subvention

pytestmark = pytest.mark.django_db


class TestBuildDgclSubvention:
    """`_build_dgcl_subvention` ne fait qu'un `Subvention(...)` non
    enregistré (cf. `import_dgcl_subventions` pour le `bulk_create`)."""

    def test_builds_an_unsaved_dgcl_subvention(self):
        DepartementFactory(insee_code="75")
        CommuneFactory(insee_code="75056")

        row = {
            "exercice": "2024",
            "dispositif": "detr",
            "beneficiaire_siren": "123456789",
            "intitule": "Rénovation école",
            "cout_ht": "1000,00",
            "subvention": "500,00",
            "departement": "75",
            "code_insee": "75056",
        }

        subvention = _build_dgcl_subvention(row)

        assert subvention.pk is None
        assert subvention.source == Subvention.SOURCE_DGCL
        assert subvention.exercice == 2024
        assert subvention.dispositif == "DETR"
        assert subvention.intitule == "Rénovation école"
        assert subvention.cout_total == 1000
        assert subvention.montant_attribue == 500
        assert subvention.departement.insee_code == "75"
        assert subvention.commune.insee_code == "75056"
        assert subvention.importer_key == ""

    def test_two_identical_rows_get_the_same_importer_key(self):
        row = {
            "exercice": "2024",
            "dispositif": "DETR",
            "beneficiaire_siren": "123456789",
            "intitule": "Rénovation école",
            "cout_ht": "1000",
            "subvention": "500",
        }

        first = _build_dgcl_subvention(row)
        second = _build_dgcl_subvention(row)

        assert first.importer_key == second.importer_key
        assert first.importer_key == ""

    @pytest.mark.parametrize(
        "missing_field",
        ["exercice", "dispositif", "beneficiaire_siren", "intitule"],
    )
    def test_skips_row_missing_a_required_field(self, missing_field):
        row = {
            "exercice": "2024",
            "dispositif": "DETR",
            "beneficiaire_siren": "123456789",
            "intitule": "Rénovation école",
            "cout_ht": "1000",
            "subvention": "500",
        }
        row[missing_field] = ""

        assert _build_dgcl_subvention(row) is None

    def test_skips_dsid_rows(self):
        row = {
            "exercice": "2024",
            "dispositif": "dsid",
            "beneficiaire_siren": "123456789",
            "intitule": "Rénovation route départementale",
            "cout_ht": "1000",
            "subvention": "500",
        }

        assert _build_dgcl_subvention(row) is None


class TestImportDgclSubventions:
    """Nouveau paradigme DGCL : pas d'upsert, tout est reconstruit à chaque
    import (cf. Subvention.__doc__ et import_dgcl_subventions)."""

    CSV_URL = "https://example.com/dgcl.csv"

    def _mock_dataset_and_csv(self, csv_text):
        responses.add(
            responses.GET,
            DGCL_API_URL,
            json={
                "resources": [
                    {"title": "DGCL 2024", "url": self.CSV_URL, "format": "csv"}
                ]
            },
        )
        responses.add(
            responses.GET,
            self.CSV_URL,
            body=csv_text.encode("utf-8-sig"),
        )

    @responses.activate
    def test_wipes_existing_dgcl_rows_and_recreates_from_csv(self):
        Subvention.objects.create(
            source=Subvention.SOURCE_DGCL,
            siren="000000000",
            exercice=2020,
            dispositif="DETR",
            programme=119,
            intitule="Ancienne ligne",
            cout_total=1,
        )
        csv_text = (
            "exercice;dispositif;beneficiaire_siren;intitule;cout_ht;subvention\n"
            "2024;DETR;123456789;Rénovation école;1000;500\n"
        )
        self._mock_dataset_and_csv(csv_text)

        import_dgcl_subventions()

        dgcl_rows = Subvention.objects.filter(source=Subvention.SOURCE_DGCL)
        assert dgcl_rows.count() == 1
        assert dgcl_rows.get().siren == "123456789"

    @responses.activate
    def test_keeps_duplicate_rows(self):
        csv_text = (
            "exercice;dispositif;beneficiaire_siren;intitule;cout_ht;subvention\n"
            "2024;DETR;123456789;Rénovation école;1000;500\n"
            "2024;DETR;123456789;Rénovation école;1000;500\n"
        )
        self._mock_dataset_and_csv(csv_text)

        import_dgcl_subventions()

        assert Subvention.objects.filter(siren="123456789").count() == 2

    @responses.activate
    def test_does_not_touch_fonds_vert_rows(self):
        Subvention.objects.create(
            source=Subvention.SOURCE_FONDS_VERT,
            siren="217500569",
            exercice=2026,
            dispositif="FONDS VERT",
            programme=380,
            intitule="Isolation mairie",
            cout_total=400,
            dossier_number=42,
        )
        self._mock_dataset_and_csv(
            "exercice;dispositif;beneficiaire_siren;intitule;cout_ht;subvention\n"
        )

        import_dgcl_subventions()

        assert (
            Subvention.objects.filter(source=Subvention.SOURCE_FONDS_VERT).count() == 1
        )


@pytest.mark.parametrize(
    "raw,expected",
    [("42", 42), (" 42 ", 42), ("", None), (None, None), ("abc", None)],
)
def test_parse_int(raw, expected):
    assert _parse_int(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1000,50", 1000.50),
        ("1 000,50", 1000.50),
        ("1000.50", 1000.50),
        ("", 0),
        (None, 0),
        ("abc", 0),
    ],
)
def test_parse_decimal(raw, expected):
    assert _parse_decimal(raw) == expected
