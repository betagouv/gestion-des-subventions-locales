import pytest
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError

from gsl_core.models import Arrondissement, Departement, Perimetre, Region
from gsl_core.tests.factories import (
    ArrondissementFactory,
    DepartementFactory,
    RegionFactory,
)
from gsl_projet.constants import (
    DOTATION_DETR,
    DOTATION_DSIL,
    PROJET_STATUS_ACCEPTED,
    PROJET_STATUS_DISMISSED,
    PROJET_STATUS_PROCESSING,
    PROJET_STATUS_REFUSED,
)
from gsl_projet.tests.factories import DotationProjetFactory, ProjetFactory

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
def dept_14(region_normandie) -> Departement:
    return DepartementFactory(insee_code="14", name="Calvados", region=region_normandie)


@pytest.fixture
def arr_paris_centre(dept_75) -> Arrondissement:
    return ArrondissementFactory(
        insee_code="75101", name="Paris Centre", departement=dept_75
    )


@pytest.fixture
def arr_le_havre(dept_76) -> Arrondissement:
    return ArrondissementFactory(insee_code="762", name="Le Havre", departement=dept_76)


@pytest.fixture
def arr_rouen(dept_76) -> Arrondissement:
    return ArrondissementFactory(insee_code="763", name="Rouen", departement=dept_76)


@pytest.fixture
def arr_bayeux(dept_14) -> Arrondissement:
    return ArrondissementFactory(insee_code="141", name="Bayeux", departement=dept_14)


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


def test_clean_perimetre_with_departement_but_without_region(dept_76):
    """Test qu'un périmètre avec département mais sans région lève une erreur"""
    perimetre = Perimetre(region=None, departement=dept_76)
    with pytest.raises(ObjectDoesNotExist):
        perimetre.clean()


def test_save_invalid_perimetre(region_idf, dept_76):
    """Test que save() appelle clean() et empêche la sauvegarde d'un périmètre invalide"""
    perimetre = Perimetre(region=region_idf, departement=dept_76)

    with pytest.raises(ValidationError) as exc_info:
        perimetre.save()

    assert exc_info.value.message_dict["departement"][0] == (
        "Le département doit appartenir à la même région que le périmètre."
    )


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


def test_unicity_by_perimeter(region_idf, dept_75):
    perimetre = Perimetre(region=region_idf, departement=dept_75)
    perimetre_bis = Perimetre(region=region_idf, departement=dept_75)
    perimetre.save()

    with pytest.raises(IntegrityError) as exc_info:
        perimetre_bis.save()

    assert "unicity_by_perimeter" in exc_info.value.args[0]


@pytest.fixture
def perimetre_region_idf(region_idf) -> Perimetre:
    return Perimetre(region=region_idf, departement=None, arrondissement=None)


@pytest.fixture
def perimetre_departement_75(region_idf, dept_75) -> Perimetre:
    return Perimetre(region=region_idf, departement=dept_75, arrondissement=None)


@pytest.fixture
def perimetre_arr_paris_centre(region_idf, dept_75, arr_paris_centre) -> Perimetre:
    return Perimetre(
        region=region_idf, departement=dept_75, arrondissement=arr_paris_centre
    )


@pytest.fixture
def perimetre_region_normandie(region_normandie) -> Perimetre:
    return Perimetre(region=region_normandie, departement=None, arrondissement=None)


@pytest.fixture
def perimetre_departement_76(region_normandie, dept_76) -> Perimetre:
    return Perimetre(region=region_normandie, departement=dept_76, arrondissement=None)


@pytest.fixture
def perimetre_arrondissement_lehavre(
    region_normandie, dept_76, arr_le_havre
) -> Perimetre:
    return Perimetre(
        region=region_normandie, departement=dept_76, arrondissement=arr_le_havre
    )


contain_test_data = (
    # Region ---------------------------------------------------------------------------
    (
        "perimetre_region_idf",
        "perimetre_departement_75",
        True,
        "Region contains its Departements",
    ),
    (
        "perimetre_region_idf",
        "perimetre_region_idf",
        False,
        "Region does not contain itself",
    ),
    (
        "perimetre_region_idf",
        "perimetre_arr_paris_centre",
        True,
        "Region contains its arrondissements",
    ),
    (
        "perimetre_region_normandie",
        "perimetre_departement_75",
        False,
        "Region does not contain a Departement from another Region",
    ),
    (
        "perimetre_region_normandie",
        "perimetre_region_idf",
        False,
        "Region does not contain another region",
    ),
    (
        "perimetre_region_normandie",
        "perimetre_arr_paris_centre",
        False,
        "Region does not contain an arrondissement from another region",
    ),
    # Departement ----------------------------------------------------------------------
    (
        "perimetre_departement_75",
        "perimetre_region_idf",
        False,
        "Departement does not contain its region",
    ),
    (
        "perimetre_departement_75",
        "perimetre_departement_75",
        False,
        "Departement does not contain itself",
    ),
    (
        "perimetre_departement_75",
        "perimetre_departement_76",
        False,
        "Departement does not contain another departement",
    ),
    (
        "perimetre_departement_75",
        "perimetre_arr_paris_centre",
        True,
        "Departement contains its Arrondissements",
    ),
    (
        "perimetre_departement_76",
        "perimetre_arr_paris_centre",
        False,
        "Departement does not contain an arrondissement from another departement",
    ),
    # Arrondissement -------------------------------------------------------------------
    (
        "perimetre_arr_paris_centre",
        "perimetre_departement_75",
        False,
        "Arrondissement does not contain its Departement",
    ),
    (
        "perimetre_arr_paris_centre",
        "perimetre_region_idf",
        False,
        "Arrondissement does not contain its Region",
    ),
    (
        "perimetre_arr_paris_centre",
        "perimetre_arr_paris_centre",
        False,
        "Arrondissement does not contain itself",
    ),
    (
        "perimetre_arr_paris_centre",
        "perimetre_arrondissement_lehavre",
        False,
        "Arrondissement does not contain another arrondissement",
    ),
)


@pytest.mark.parametrize("container,arg,expected,comment", contain_test_data)
def test_perimetre_contains(container, arg, expected, comment, request):
    container: Perimetre = request.getfixturevalue(container)
    argument: Perimetre = request.getfixturevalue(arg)
    assert container.contains(argument) == expected, comment


@pytest.mark.django_db
def test_type_and_name_property_for_region(region_idf):
    perimetre = Perimetre.objects.create(region=region_idf)
    assert perimetre.type == "Région"
    assert perimetre.entity_name == "Île-de-France"


@pytest.mark.django_db
def test_type_and_name_property_for_departement(region_idf, dept_75):
    perimetre = Perimetre.objects.create(region=region_idf, departement=dept_75)
    assert perimetre.type == "Département"
    assert perimetre.entity_name == "Paris"


def test_type_and_name_property_for_arrondissement(
    region_idf, dept_75, arr_paris_centre
):
    perimetre = Perimetre.objects.create(
        region=region_idf,
        departement=dept_75,
        arrondissement=arr_paris_centre,
    )
    assert perimetre.type == "Arrondissement"
    assert perimetre.entity_name == "Paris Centre"


@pytest.mark.django_db
def test_get_perimetre_children(
    region_normandie,
    dept_76,
    dept_14,
    arr_le_havre,
    arr_rouen,
    arr_bayeux,
    region_idf,
    dept_75,
    arr_paris_centre,
):
    perimetre_region_normandie = Perimetre.objects.create(region=region_normandie)
    perimetre_departement_76 = Perimetre.objects.create(
        region=region_normandie, departement=dept_76
    )
    perimetre_departement_14 = Perimetre.objects.create(
        region=region_normandie, departement=dept_14
    )
    perimetre_arr_lehavre = Perimetre.objects.create(
        region=region_normandie, departement=dept_76, arrondissement=arr_le_havre
    )
    Perimetre.objects.create(
        region=region_normandie, departement=dept_76, arrondissement=arr_rouen
    )
    Perimetre.objects.create(
        region=region_normandie, departement=dept_14, arrondissement=arr_bayeux
    )
    Perimetre.objects.create(
        region=region_idf,
        departement=dept_75,
        arrondissement=arr_paris_centre,
    )

    children_of_dept_76 = perimetre_departement_76.children()
    assert len(children_of_dept_76) == 2  # 2 arrondissements in 76
    assert perimetre_departement_76 not in children_of_dept_76
    assert perimetre_departement_14 not in children_of_dept_76
    assert perimetre_arr_lehavre in children_of_dept_76

    children_of_region_normandie = perimetre_region_normandie.children()
    assert (
        len(children_of_region_normandie) == 2 + 2 + 1
    )  # 2 departements (14 76), 2 arr in 76, 1 arr in 14
    assert perimetre_departement_75 not in children_of_region_normandie
    assert perimetre_departement_76 in children_of_region_normandie
    assert perimetre_departement_14 in children_of_region_normandie
    assert perimetre_arr_lehavre in children_of_region_normandie


@pytest.mark.parametrize(
    "accepted, processing, refused, dismissed, expected_status",
    (
        (False, False, False, False, None),
        (True, False, False, False, PROJET_STATUS_ACCEPTED),
        (False, True, False, False, PROJET_STATUS_PROCESSING),
        (False, False, True, False, PROJET_STATUS_REFUSED),
        (False, False, False, True, PROJET_STATUS_DISMISSED),
        (True, True, False, False, PROJET_STATUS_ACCEPTED),
        (True, False, True, False, PROJET_STATUS_ACCEPTED),
        (True, False, False, True, PROJET_STATUS_ACCEPTED),
        (False, True, True, False, PROJET_STATUS_PROCESSING),
        (False, True, False, True, PROJET_STATUS_PROCESSING),
        (False, False, True, True, PROJET_STATUS_REFUSED),
    ),
)
def test_status_mixed_dotations(
    accepted, processing, refused, dismissed, expected_status
):
    projet = ProjetFactory()
    current_dotation = DOTATION_DETR

    if accepted:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_ACCEPTED,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if processing:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_PROCESSING,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if refused:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_REFUSED,
            dotation=current_dotation,
        )
        current_dotation = DOTATION_DSIL
    if dismissed:
        DotationProjetFactory(
            projet=projet,
            status=PROJET_STATUS_DISMISSED,
            dotation=current_dotation,
        )

    assert projet.status == expected_status
