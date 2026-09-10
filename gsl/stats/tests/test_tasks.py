import pytest
import responses

from gsl_core.tests.factories import CommuneFactory, DepartementFactory

from ..models import Subvention
from ..tasks import (
    DGCL_API_URL,
    FONDS_VERT_DISPOSITIF,
    FONDS_VERT_PROGRAMME,
    _build_dgcl_subvention,
    _import_fonds_vert_dossier,
    _parse_decimal,
    _parse_int,
    fetch_subventions_dgcl,
)

pytestmark = pytest.mark.django_db


class TestBuildDgclSubvention:
    """`_build_dgcl_subvention` ne fait qu'un `Subvention(...)` non
    enregistré (cf. `fetch_subventions_dgcl` pour le `bulk_create`)."""

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
        assert subvention.unique_key

    def test_two_identical_rows_get_distinct_unique_keys(self):
        # Les doublons sont désormais conservés tels quels (cf.
        # Subvention.__doc__) : le hash ne doit donc jamais entrer en
        # collision entre deux lignes de contenu identique.
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

        assert first.unique_key != second.unique_key

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


class TestFetchSubventionsDgcl:
    """Nouveau paradigme DGCL : pas d'upsert, tout est reconstruit à chaque
    import (cf. Subvention.__doc__ et fetch_subventions_dgcl)."""

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

        fetch_subventions_dgcl()

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

        fetch_subventions_dgcl()

        assert Subvention.objects.filter(siren="123456789").count() == 2

    @responses.activate
    def test_does_not_touch_fonds_vert_rows(self):
        Subvention.objects.create(
            source=Subvention.SOURCE_FONDS_VERT,
            siren="217500569",
            exercice=2026,
            dispositif=FONDS_VERT_DISPOSITIF,
            programme=380,
            intitule="Isolation mairie",
            cout_total=400,
            dossier_number=42,
        )
        self._mock_dataset_and_csv(
            "exercice;dispositif;beneficiaire_siren;intitule;cout_ht;subvention\n"
        )

        fetch_subventions_dgcl()

        assert (
            Subvention.objects.filter(source=Subvention.SOURCE_FONDS_VERT).count() == 1
        )


class TestImportFondsVertDossier:
    def _item(self, **socle_commun_overrides):
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
