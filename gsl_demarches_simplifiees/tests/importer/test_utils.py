import pytest

from gsl_core.models import Arrondissement, Departement
from gsl_core.tests.factories import (
    ArrondissementFactory,
    DepartementFactory,
    RegionFactory,
)
from gsl_demarches_simplifiees.importer.utils import (
    get_arrondissement_from_value,
    get_categorie_detr_from_value,
    get_departement_from_field_label,
    get_departement_from_value,
)
from gsl_demarches_simplifiees.models import CategorieDetr
from gsl_demarches_simplifiees.tests.factories import (
    CategorieDetrFactory,
    DemarcheFactory,
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
    with pytest.raises(Departement.DoesNotExist):
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
def test_get_departement_from_value_raises_when_departement_does_not_exist(caplog):
    with pytest.raises(Departement.DoesNotExist):
        get_departement_from_value("99 - Inexist-ant")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "Departement not found."
    assert record.insee_code == "99"
    assert record.value == "99 - Inexist-ant"


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


@pytest.mark.django_db
def test_get_arrondissement_from_value_disambiguates_by_departement():
    region = RegionFactory()
    dep_10 = DepartementFactory(region=region, insee_code="10", name="Aube")
    dep_52 = DepartementFactory(region=region, insee_code="52", name="Haute-Marne")
    ArrondissementFactory(departement=dep_10, insee_code="101", name="Bar-sur-Aube")
    arr_52 = ArrondissementFactory(
        departement=dep_52, insee_code="521", name="Bar-sur-Aube"
    )
    result = get_arrondissement_from_value(
        "52 - Haute-Marne - arrondissement de Bar-sur-Aube"
    )
    assert result == arr_52


def test_get_arrondissement_from_value_raises_when_no_pattern():
    with pytest.raises(ValueError, match="Arrondissement not found in field value"):
        get_arrondissement_from_value("Some value without arrondissement pattern")


@pytest.mark.django_db
def test_get_arrondissement_from_value_raises_when_arrondissement_does_not_exist(
    caplog,
):
    with pytest.raises(Arrondissement.DoesNotExist):
        get_arrondissement_from_value("10 - Aube - arrondissement de Inexist-ant")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "Arrondissement not found."
    assert record.value == "10 - Aube - arrondissement de Inexist-ant"


# --- get_categorie_detr_from_value ---


@pytest.mark.django_db
def test_get_categorie_detr_from_value_returns_existing_categorie():
    """When a CategorieDetr already exists for (demarche, label, departement), returns it."""
    demarche = DemarcheFactory(ds_number=131016)
    region = RegionFactory()
    departement = DepartementFactory(
        region=region, insee_code="87", name="Haute-Vienne"
    )
    existing = CategorieDetrFactory(
        demarche=demarche,
        departement=departement,
        label="Catégorie prioritaire A",
        active=True,
    )

    result = get_categorie_detr_from_value(
        value="Catégorie prioritaire A",
        departement=departement,
        ds_demarche_number=demarche.ds_number,
    )

    assert result == existing
    assert result.label == "Catégorie prioritaire A"
    assert result.active is True
    assert (
        CategorieDetr.objects.filter(
            demarche=demarche, label="Catégorie prioritaire A"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_get_categorie_detr_from_value_creates_categorie_when_missing():
    """When no CategorieDetr exists, creates one with active=False and returns it."""
    demarche = DemarcheFactory(ds_number=131017)
    region = RegionFactory()
    departement = DepartementFactory(region=region, insee_code="91", name="Essonne")

    result = get_categorie_detr_from_value(
        value="Nouvelle catégorie",
        departement=departement,
        ds_demarche_number=demarche.ds_number,
    )

    assert result is not None
    assert result.label == "Nouvelle catégorie"
    assert result.demarche_id == demarche.pk
    assert result.departement_id == departement.pk
    assert result.active is False
    assert result.deactivated_at is not None


@pytest.mark.django_db
def test_get_categorie_detr_from_value_logs_when_created(caplog):
    """When a new CategorieDetr is created, a log record is emitted."""
    demarche = DemarcheFactory(ds_number=131018)
    region = RegionFactory()
    departement = DepartementFactory(region=region, insee_code="10", name="Aube")

    get_categorie_detr_from_value(
        value="Catégorie créée",
        departement=departement,
        ds_demarche_number=demarche.ds_number,
    )

    created_records = [
        r for r in caplog.records if "CategorieDetr created" in r.message
    ]
    assert len(created_records) == 1
    assert getattr(created_records[0], "ds_demarche_number") == demarche.ds_number
    assert getattr(created_records[0], "value") == "Catégorie créée"
    assert getattr(created_records[0], "departement") == departement


@pytest.mark.django_db
def test_get_categorie_detr_from_value_does_not_log_when_existing(caplog):
    """When CategorieDetr already exists, no 'CategorieDetr created' log is emitted."""
    demarche = DemarcheFactory(ds_number=131019)
    region = RegionFactory()
    departement = DepartementFactory(region=region, insee_code="67", name="Bas-Rhin")
    CategorieDetrFactory(
        demarche=demarche,
        departement=departement,
        label="Déjà là",
    )

    get_categorie_detr_from_value(
        value="Déjà là",
        departement=departement,
        ds_demarche_number=demarche.ds_number,
    )

    created_records = [
        r for r in caplog.records if "CategorieDetr created" in r.message
    ]
    assert len(created_records) == 0
