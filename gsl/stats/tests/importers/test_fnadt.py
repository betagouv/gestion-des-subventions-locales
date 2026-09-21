import io

import openpyxl
import pytest

from gsl_core.tests.factories import CommuneFactory

from ...importers.fnadt import (
    FNADT_DISPOSITIF,
    FNADT_PROGRAMME,
    FNADT_SHEET_NAME,
    FnadtRowSkipped,
    _build_fnadt_subvention,
    _find_fnadt_column,
    _resolve_fnadt_columns,
    import_fnadt_subventions,
)
from ...models import Subvention
from ..factories import SubventionFactory

pytestmark = pytest.mark.django_db

HEADER = [
    "Année",
    "région",
    "Code INSEE commune/ Code SIREN EPCI du lieu du projet soutenu",
    "Commentaires :\nquelques mots",
    "Coût total du projet",
    "Montant subvention FNADT attribuée (AE)",
]


def _build_fnadt_workbook(rows, header=HEADER, sheet_name=FNADT_SHEET_NAME):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    # Une feuille récapitulative (tableau croisé dynamique) qui doit être
    # ignorée, comme dans le vrai classeur (cf. FNADT_SHEET_NAME).
    workbook.create_sheet("Feuil1")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestBuildFnadtSubvention:
    """`_build_fnadt_subvention` ne fait qu'un `Subvention(...)` non
    enregistré (cf. `import_fnadt_subventions` pour le `bulk_create`)."""

    def _columns(self):
        return _resolve_fnadt_columns(HEADER)

    def test_builds_an_unsaved_fnadt_subvention_when_commune_is_resolved(self):
        commune = CommuneFactory(insee_code="43157", siren="200042489")
        row = [2024, "AURA", "43157", "Rénovation école", 1000, 500]

        subvention = _build_fnadt_subvention(self._columns(), row)

        assert subvention.pk is None
        assert subvention.source == Subvention.SOURCE_FNADT
        assert subvention.exercice == 2024
        assert subvention.dispositif == FNADT_DISPOSITIF
        assert subvention.programme == FNADT_PROGRAMME
        assert subvention.siren == "200042489"
        assert subvention.intitule == "Rénovation école"
        assert subvention.commune == commune
        assert subvention.departement == commune.departement
        assert subvention.cout_total == 1000
        assert subvention.montant_attribue == 500

    def test_skips_row_missing_annee(self):
        row = [None, "AURA", "43157", "Rénovation école", 1000, 500]

        with pytest.raises(FnadtRowSkipped, match="année manquante"):
            _build_fnadt_subvention(self._columns(), row)

    def test_skips_row_when_commune_is_not_found(self):
        row = [2024, "AURA", "99999", "Rénovation école", 1000, 500]

        with pytest.raises(FnadtRowSkipped, match="commune introuvable"):
            _build_fnadt_subvention(self._columns(), row)

    def test_skips_row_when_commune_has_no_siren(self):
        CommuneFactory(insee_code="43157", siren="")
        row = [2024, "AURA", "43157", "Rénovation école", 1000, 500]

        with pytest.raises(FnadtRowSkipped, match="commune sans SIREN enregistré"):
            _build_fnadt_subvention(self._columns(), row)

    def test_uses_the_value_directly_when_it_is_already_a_siren(self):
        # La colonne contient, selon les lignes, un code INSEE commune (5
        # caractères) ou directement le SIREN d'un EPCI (9 chiffres) — cf.
        # _resolve_fnadt_siren.
        row = [
            2024,
            "Occitanie",
            "200066363",
            "Réhabilitation base nautique",
            1000,
            500,
        ]

        subvention = _build_fnadt_subvention(self._columns(), row)

        assert subvention.siren == "200066363"
        assert subvention.commune is None
        assert subvention.departement is None

    def test_repads_a_commune_code_missing_its_leading_zero(self):
        # Excel a parfois stocké la cellule comme un nombre, ce qui fait
        # sauter le zéro de tête du code INSEE (ex. "05110" -> 5110).
        commune = CommuneFactory(insee_code="05110", siren="200023456")
        row = [2024, "PACA", 5110, "Rénovation mairie", 1000, 500]

        subvention = _build_fnadt_subvention(self._columns(), row)

        assert subvention.siren == "200023456"
        assert subvention.commune == commune

    def test_repads_a_commune_code_stored_as_a_float(self):
        commune = CommuneFactory(insee_code="05110", siren="200023456")
        row = [2024, "PACA", 5110.0, "Rénovation mairie", 1000, 500]

        subvention = _build_fnadt_subvention(self._columns(), row)

        assert subvention.siren == "200023456"
        assert subvention.commune == commune

    def test_uses_the_siren_directly_when_the_cell_has_both_values(self):
        # Certaines cellules renseignent à la fois le code INSEE commune et
        # le SIREN de l'EPCI, une valeur par ligne (avec des espaces de
        # séparation par milliers dans le SIREN) : on retient le SIREN.
        row = [2024, "AURA", "25335\n200 023 075", "Rénovation mairie", 1000, 500]

        subvention = _build_fnadt_subvention(self._columns(), row)

        assert subvention.siren == "200023075"
        assert subvention.commune is None
        assert subvention.departement is None

    def test_resolves_a_lowercase_corse_code_against_an_uppercase_commune(self):
        commune = CommuneFactory(insee_code="2B267", siren="200023456")
        row = [2024, "Corse", "2b267", "Rénovation mairie", 1000, 500]

        subvention = _build_fnadt_subvention(self._columns(), row)

        assert subvention.siren == "200023456"
        assert subvention.commune == commune

    def test_uses_the_first_9_digits_when_the_value_is_a_siret(self):
        row = [2024, "AURA", "20002307500123", "Rénovation mairie", 1000, 500]

        subvention = _build_fnadt_subvention(self._columns(), row)

        assert subvention.siren == "200023075"
        assert subvention.commune is None
        assert subvention.departement is None


class TestImportFnadtSubventions:
    """Comme pour les données DGCL, le classeur est republié dans son
    intégralité à chaque mise à jour et n'a pas d'identifiant stable par
    ligne : pas d'upsert, tout est reconstruit à chaque import."""

    def test_wipes_existing_fnadt_rows_and_recreates_from_workbook(self):
        SubventionFactory(source=Subvention.SOURCE_FNADT, siren="000000000")
        CommuneFactory(insee_code="43157", siren="200042489")
        content = _build_fnadt_workbook(
            [[2024, "AURA", "43157", "Rénovation école", 1000, 500]]
        )

        bilan = import_fnadt_subventions(content)

        assert bilan == {"imported": 1, "skipped": 0}
        fnadt_rows = Subvention.objects.filter(source=Subvention.SOURCE_FNADT)
        assert fnadt_rows.count() == 1
        assert fnadt_rows.get().siren == "200042489"

    def test_does_not_touch_other_source_rows(self):
        SubventionFactory(source=Subvention.SOURCE_DGCL, siren="111111111")
        content = _build_fnadt_workbook([])

        import_fnadt_subventions(content)

        assert Subvention.objects.filter(source=Subvention.SOURCE_DGCL).count() == 1

    def test_skips_a_fully_empty_row(self):
        CommuneFactory(insee_code="43157", siren="200042489")
        content = _build_fnadt_workbook(
            [
                [2024, "AURA", "43157", "Rénovation école", 1000, 500],
                [None, None, None, None, None, None],
            ]
        )

        bilan = import_fnadt_subventions(content)

        assert bilan == {"imported": 1, "skipped": 0}

    def test_raises_when_the_header_is_missing_an_expected_column(self):
        # Échec net (fail fast) plutôt que d'invalider chaque ligne une par
        # une : une colonne manquante dans l'en-tête est un problème de
        # classeur, pas de ligne — cf. `_find_fnadt_column`.
        header_missing_montant = HEADER[:-1]
        content = _build_fnadt_workbook(
            [[2024, "AURA", "43157", "Rénovation école", 1000]],
            header=header_missing_montant,
        )

        with pytest.raises(ValueError, match="Montant subvention FNADT"):
            import_fnadt_subventions(content)

        assert not Subvention.objects.exists()

    def test_counts_unresolved_rows_as_skipped(self):
        content = _build_fnadt_workbook(
            [[2024, "AURA", "99999", "Rénovation école", 1000, 500]]
        )

        bilan = import_fnadt_subventions(content)

        assert bilan == {"imported": 0, "skipped": 1}
        assert not Subvention.objects.exists()


class TestFindFnadtColumn:
    def test_finds_a_column_by_case_insensitive_prefix(self):
        assert _find_fnadt_column(HEADER, "coût total") == 4
        assert _find_fnadt_column(HEADER, "année") == 0

    def test_does_not_match_a_name_in_the_middle_of_the_title(self):
        # Contrairement à une recherche par sous-chaîne, seul un préfixe de
        # l'intitulé compte : ça évite de matcher la mauvaise colonne au
        # hasard d'un mot commun ailleurs dans le titre.
        with pytest.raises(ValueError, match="total du projet"):
            _find_fnadt_column(HEADER, "total du projet")

    def test_raises_when_not_found(self):
        with pytest.raises(ValueError, match="montant"):
            _find_fnadt_column(["Année"], "montant")
