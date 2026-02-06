# --- _get_departement_from_field_label ---


import pytest

from gsl_core.tests.factories import DepartementFactory, RegionFactory
from gsl_demarches_simplifiees.importer.utils import get_departement_from_field_label


@pytest.mark.django_db
def test_get_departement_from_field_label_returns_departement_when_label_matches():
    region = RegionFactory()
    dep_87 = DepartementFactory(region=region, insee_code="87", name="Haute-Vienne")
    result = get_departement_from_field_label(
        "Catégories prioritaires (87 - Haute-Vienne)"
    )
    assert result == dep_87
    assert result.insee_code == "87"


@pytest.mark.django_db
def test_get_departement_from_field_label_accepts_label_with_optional_question_mark():
    region = RegionFactory()
    dep_01 = DepartementFactory(region=region, insee_code="01", name="Ain")
    result = get_departement_from_field_label(
        "Arrondissement du demandeur (01 - Ain) ?"
    )
    assert result == dep_01
    assert result.insee_code == "01"


@pytest.mark.django_db
def test_get_departement_from_field_label_accepts_corse_style_codes():
    region = RegionFactory()
    dep_2a = DepartementFactory(region=region, insee_code="2A", name="Corse-du-Sud")
    result = get_departement_from_field_label(
        "Catégories prioritaires (2A - Corse-du-Sud)"
    )
    assert result == dep_2a
    assert result.insee_code == "2A"


def test_get_departement_from_field_label_raises_when_no_pattern_in_label():
    with pytest.raises(ValueError, match="Departement not found in field label"):
        get_departement_from_field_label("Some field without département pattern")


@pytest.mark.django_db
def test_get_departement_from_field_label_raises_when_departement_does_not_exist():
    with pytest.raises(ValueError, match="Departement not found: 99"):
        get_departement_from_field_label("Catégories prioritaires (99 - Inexist-ant)")
