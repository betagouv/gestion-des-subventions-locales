import pytest
from django.test import RequestFactory

from gsl_core.tests.factories import (
    CollegueFactory,
    PerimetreDepartementalFactory,
)
from gsl_projet.constants import DOTATION_DETR, DOTATION_DSIL
from gsl_simulation.filters import SimulationProjetFilters

pytestmark = pytest.mark.django_db


@pytest.fixture
def perimetre():
    return PerimetreDepartementalFactory()


@pytest.fixture
def user(perimetre):
    return CollegueFactory(perimetre=perimetre)


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory, user):
    request = request_factory.get("/")
    request.user = user
    request.resolver_match = type(
        "MockResolverMatch", (), {"kwargs": {"slug": "ma-simulation"}}
    )()
    return request


def test_fixed_fields_show_detr_category_on_detr_simulation(mock_request):
    """On a DETR simulation page, the DETR category sits in the fixed row and
    the DSIL category is absent."""
    filterset = SimulationProjetFilters(request=mock_request, dotation=DOTATION_DETR)
    fixed_names = [field.name for field in filterset.fixed_fields]
    assert "categorie_detr" in fixed_names
    assert "categorie_dsil" not in fixed_names


def test_fixed_fields_show_dsil_category_on_dsil_simulation(mock_request):
    """On a DSIL simulation page, the DSIL category sits in the fixed row and
    the DETR category is absent."""
    filterset = SimulationProjetFilters(request=mock_request, dotation=DOTATION_DSIL)
    fixed_names = [field.name for field in filterset.fixed_fields]
    assert "categorie_dsil" in fixed_names
    assert "categorie_detr" not in fixed_names
