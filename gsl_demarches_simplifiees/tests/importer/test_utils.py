import pytest

from gsl_core.tests.factories import (
    ArrondissementFactory,
    DepartementFactory,
    RegionFactory,
)
from gsl_demarches_simplifiees.importer.utils import (
    get_arrondissement_from_value,
    get_departement_from_field_label,
    get_departement_from_value,
)


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


# --- get_departement_from_value ---


@pytest.mark.django_db
def test_get_departement_from_value_returns_departement_when_value_matches():
    region = RegionFactory()
    dep = DepartementFactory(region=region, insee_code="87", name="Haute-Vienne")
    result = get_departement_from_value("87 - Haute-Vienne")
    assert result == dep
    assert result.insee_code == "87"


@pytest.mark.django_db
def test_get_departement_from_value_accepts_essonne():
    region = RegionFactory()
    dep = DepartementFactory(region=region, insee_code="91", name="Essonne")
    result = get_departement_from_value("91 - Essonne")
    assert result == dep
    assert result.insee_code == "91"


@pytest.mark.django_db
def test_get_departement_from_value_accepts_corse_style_codes():
    region = RegionFactory()
    dep_2a = DepartementFactory(region=region, insee_code="2A", name="Corse-du-Sud")
    result = get_departement_from_value("2A - Corse-du-Sud")
    assert result == dep_2a
    assert result.insee_code == "2A"


@pytest.mark.django_db
def test_get_departement_from_value_accepts_three_digit_codes():
    region = RegionFactory()
    dep_976 = DepartementFactory(
        region=region, insee_code="976", name="Nouvelle-Calédonie"
    )
    result = get_departement_from_value("976 - Nouvelle-Calédonie")
    assert result == dep_976
    assert result.insee_code == "976"


def test_get_departement_from_value_raises_when_no_pattern():
    with pytest.raises(ValueError, match="Departement not found in field value"):
        get_departement_from_value("Some value without code - name pattern")


@pytest.mark.django_db
def test_get_departement_from_value_raises_when_departement_does_not_exist():
    with pytest.raises(ValueError, match="Departement not found: 99"):
        get_departement_from_value("99 - Inexist-ant")


# --- get_arrondissement_from_value ---


@pytest.mark.django_db
def test_get_arrondissement_from_value_returns_arrondissement_when_value_matches():
    region = RegionFactory()
    departement = DepartementFactory(region=region, insee_code="10", name="Aube")
    arr = ArrondissementFactory(
        departement=departement,
        insee_code="101",
        name="Bar-sur-Aube",
    )
    result = get_arrondissement_from_value("10 - Aube - arrondissement de Bar-sur-Aube")
    assert result == arr
    assert result.name == "Bar-sur-Aube"


@pytest.mark.django_db
def test_get_arrondissement_from_value_returns_arrondissement_with_hyphenated_name():
    region = RegionFactory()
    departement = DepartementFactory(region=region, insee_code="67", name="Bas-Rhin")
    arr = ArrondissementFactory(
        departement=departement,
        insee_code="672",
        name="Haguenau-Wissembourg",
    )
    result = get_arrondissement_from_value(
        "67 - Bas-Rhin - arrondissement de Haguenau-Wissembourg"
    )
    assert result == arr
    assert result.name == "Haguenau-Wissembourg"


def test_get_arrondissement_from_value_raises_when_no_pattern():
    with pytest.raises(ValueError, match="Arrondissement not found in field value"):
        get_arrondissement_from_value("Some value without arrondissement pattern")


@pytest.mark.django_db
def test_get_arrondissement_from_value_raises_when_arrondissement_does_not_exist():
    with pytest.raises(ValueError, match="Arrondissement not found: Inexist-ant"):
        get_arrondissement_from_value("10 - Aube - arrondissement de Inexist-ant")
