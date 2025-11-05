import pytest

from gsl_demarches_simplifiees.importer.demarche import _normalize_ds_label


@pytest.mark.parametrize(
    "input_label, expected",
    [
        ("Arrondissement du demandeur (01 - Ain)", "Arrondissement du demandeur"),
        ("Intitulé sans suffixe", "Intitulé sans suffixe"),
        ("Libellé avec espaces   (truc)", "Libellé avec espaces"),
        ("Texte (interne) qui continue", "Texte (interne) qui continue"),
        ("Deux suffixes (premier) (deuxième)", "Deux suffixes (premier)"),
        ("Avec espaces fin   (parenthèse)   ", "Avec espaces fin"),
        ("(Tout entre parenthèses)", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_ds_label(input_label, expected):
    assert _normalize_ds_label(input_label) == expected
