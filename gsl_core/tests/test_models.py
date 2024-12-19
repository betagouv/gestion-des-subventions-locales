import pytest
from django.core.exceptions import ValidationError

from gsl_core.models import Arrondissement, Departement, Perimetre, Region
from gsl_core.tests.factories import (
    ArrondissementFactory,
    DepartementFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def region_idf() -> Region:
    return RegionFactory(name="Île-de-France", insee_code="11")


@pytest.fixture
def region_normandie() -> Region:
    return RegionFactory(name="Normandie", insee_code="28")


@pytest.fixture
def dept_75(region_idf) -> Departement:
    return DepartementFactory(insee_code="75", name="Paris", region=region_idf)


@pytest.fixture
def dept_76(region_normandie) -> Departement:
    return DepartementFactory(
        insee_code="76", name="Seine-Maritime", region=region_normandie
    )


@pytest.fixture
def arr_paris_centre(dept_75) -> Arrondissement:
    return ArrondissementFactory(
        insee_code="75101", name="Paris Centre", departement=dept_75
    )


@pytest.fixture
def arr_le_havre(dept_76) -> Arrondissement:
    return ArrondissementFactory(insee_code="762", name="Le Havre", departement=dept_76)


def test_clean_valid_perimetre(region_idf, dept_75):
    """Test qu'un périmètre avec un département de la bonne région est valide"""
    perimetre = Perimetre(region=region_idf, departement=dept_75)
    perimetre.clean()  # Ne doit pas lever d'exception


def test_clean_invalid_perimetre(region_idf, dept_76):
    """Test qu'un périmètre avec un département d'une autre région lève une erreur"""
    perimetre = Perimetre(region=region_idf, departement=dept_76)

    with pytest.raises(ValidationError) as exc_info:
        perimetre.clean()

    assert "departement" in exc_info.value.message_dict
    assert exc_info.value.message_dict["departement"][0] == (
        "Le département doit appartenir à la même région que le périmètre."
    )


def test_save_invalid_perimetre(region_idf, dept_76):
    """Test que save() appelle clean() et empêche la sauvegarde d'un périmètre invalide"""
    perimetre = Perimetre(region=region_idf, departement=dept_76)

    with pytest.raises(ValidationError):
        perimetre.save()


def test_clean_perimetre_without_departement(region_idf):
    """Test qu'un périmètre sans département est valide"""
    perimetre = Perimetre(region=region_idf, departement=None)
    perimetre.clean()  # Ne doit pas lever d'exception


def test_clean_valid_perimetre_with_arrondissement(
    region_idf, dept_75, arr_paris_centre
):
    """Test qu'un périmètre avec un arrondissement du bon département est valide"""
    perimetre = Perimetre(
        region=region_idf, departement=dept_75, arrondissement=arr_paris_centre
    )
    perimetre.clean()  # Ne doit pas lever d'exception


def test_clean_perimetre_with_wrong_arrondissement(region_idf, dept_75, arr_le_havre):
    """Test qu'un périmètre avec un arrondissement d'un autre département lève une erreur"""
    perimetre = Perimetre(
        region=region_idf, departement=dept_75, arrondissement=arr_le_havre
    )

    with pytest.raises(ValidationError) as exc_info:
        perimetre.clean()

    assert "arrondissement" in exc_info.value.message_dict
    assert exc_info.value.message_dict["arrondissement"][0] == (
        "L'arrondissement sélectionné doit appartenir à son département."
    )


def test_clean_perimetre_with_arrondissement_without_departement(
    region_idf, arr_paris_centre
):
    """Test qu'un périmètre avec un arrondissement mais sans département lève une erreur"""
    perimetre = Perimetre(
        region=region_idf, departement=None, arrondissement=arr_paris_centre
    )

    with pytest.raises(ValidationError) as exc_info:
        perimetre.clean()

    assert "arrondissement" in exc_info.value.message_dict
    assert exc_info.value.message_dict["arrondissement"][0] == (
        "Un arrondissement ne peut être sélectionné sans département."
    )
